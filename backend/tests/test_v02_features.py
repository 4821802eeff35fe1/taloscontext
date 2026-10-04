from itertools import pairwise

"""Feature tests for v0.2 blocks P1–P14 through the HTTP API (fake providers)."""
import json
import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.jobs import scheduler
from app.models.content import ContentItem
from app.models.enums import ContentStatus
from app.models.scheduling import Schedule, ScheduleRule
from app.services.scheduling.service import (
    ScheduleService,
    ScheduleValidationError,
    validate_windows,
)
from tests.conftest import register


async def _setup(client, email="p@example.com"):
    ws = await register(client, email)
    base = f"/api/v1/workspaces/{ws}"
    flow = (await client.post(f"{base}/telegram/auth/start", json={"phone": "+15551112233"})).json()
    await client.post(f"{base}/telegram/auth/{flow['flow_id']}/code", json={"code": "1"})
    channels = (await client.get(f"{base}/channels")).json()
    cs = (await client.post(f"{base}/channel-sets", json={"name": "Net", "channel_ids": [c["id"] for c in channels]})).json()
    return ws, base, channels, cs


async def _generate(client, base, cs_id, **extra):
    r = await client.post(f"{base}/content/generate", json={"instruction": "Write about CTR", "channel_set_id": cs_id, **extra})
    assert r.status_code == 202, r.text
    assert r.json()["job"]["status"] in ("QUEUED", "SUCCESS")
    return (await client.get(f"{base}/content/{r.json()['content']['id']}")).json()


# ------------------------------------------------------------------ P1 Content Studio


@pytest.mark.asyncio
async def test_transform_creates_revision_cost_and_keeps_history(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    assert item["status"] == "DRAFT" and item["ai_cost_rub"] > "0"

    r = await client.post(f"{base}/content/{item['id']}/transform", json={"operation": "shorten"})
    assert r.status_code == 202, r.text
    job = (await client.get(f"{base}/jobs/{r.json()['id']}")).json()
    assert job["status"] == "SUCCESS" and job["metadata"]["completion_tokens"] > 0

    after = (await client.get(f"{base}/content/{item['id']}")).json()
    assert after["telegram_html"] != item["telegram_html"] and after["telegram_html"].endswith("…")
    revisions = (await client.get(f"{base}/content/{item['id']}/revisions")).json()
    assert [r["action"] for r in revisions] == ["shorten", "GENERATE_POST"]
    assert revisions[0]["is_ai"] and revisions[0]["cost_rub"] is not None and revisions[0]["version"] == 2
    assert any(d["op"] == "delete" for d in revisions[0]["diff"])

    costs = (await client.get(f"{base}/content/{item['id']}/costs")).json()
    ops = {line["operation"] for line in costs["lines"]}
    assert ops == {"GENERATE_POST", "SHORTEN"}
    assert float(costs["total_rub"]) == pytest.approx(float(after["ai_cost_rub"]))

    # restore v1 -> new version, history untouched
    v1 = revisions[-1]
    restored = (await client.post(f"{base}/content/{item['id']}/revisions/{v1['id']}/restore")).json()
    assert restored["telegram_html"] == item["telegram_html"]
    assert len((await client.get(f"{base}/content/{item['id']}/revisions")).json()) == 3


@pytest.mark.asyncio
async def test_every_transform_operation_and_fragment(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    for op in ("rewrite", "expand", "improve", "remove_cliches", "generate_headline", "generate_cta"):
        r = await client.post(f"{base}/content/{item['id']}/transform", json={"operation": op})
        assert r.status_code == 202, (op, r.text)
        assert (await client.get(f"{base}/jobs/{r.json()['id']}")).json()["status"] == "SUCCESS", op
    current = (await client.get(f"{base}/content/{item['id']}")).json()
    assert current["title"].startswith("Лучше:") and current["cta_key"] == "website"

    r = await client.post(f"{base}/content/{item['id']}/transform", json={"operation": "regenerate_fragment"})
    assert r.status_code == 422  # needs a selection
    fragment = "практичный пост"
    r = await client.post(f"{base}/content/{item['id']}/transform",
                          json={"operation": "regenerate_fragment", "selection": fragment})
    after = (await client.get(f"{base}/content/{item['id']}")).json()
    assert f"{fragment} (переписано)" in after["telegram_html"]


@pytest.mark.asyncio
async def test_autosave_conflict_detection(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    base_rev = item["latest_revision_id"]
    r = await client.patch(f"{base}/content/{item['id']}", json={"telegram_html": "<b>A</b>", "base_revision_id": base_rev})
    assert r.status_code == 200
    stale = await client.patch(f"{base}/content/{item['id']}", json={"telegram_html": "<b>B</b>", "base_revision_id": base_rev})
    assert stale.status_code == 409 and "changed elsewhere" in stale.json()["detail"]


@pytest.mark.asyncio
async def test_html_sanitized_on_save_xss(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    r = await client.patch(f"{base}/content/{item['id']}", json={
        "telegram_html": '<b>ok</b><img src=x onerror=alert(1)><script>alert(2)</script><a href="javascript:x">l</a>'})
    html = r.json()["telegram_html"]
    assert "<img" not in html and "<script" not in html and "javascript:" not in html and "<b>ok</b>" in html


# ------------------------------------------------------------------ P2 schedules / calendar / misfire


def test_overlapping_and_midnight_windows_rejected():
    with pytest.raises(ScheduleValidationError, match="overlap"):
        validate_windows([("10:00", "12:00"), ("11:30", "13:00")])
    with pytest.raises(ScheduleValidationError, match="midnight"):
        validate_windows([("22:00", "02:00")])
    assert len(validate_windows([("16:00", "18:00"), ("11:00", "13:00")])) == 2


def _schedule(**kw) -> tuple[Schedule, list[ScheduleRule]]:
    s = Schedule(id=uuid.uuid4(), workspace_id=uuid.uuid4(), name="S", timezone=kw.get("tz", "UTC"),
                 posts_per_day=kw.get("n", 3), days_of_week_json="[0,1,2,3,4,5,6]", min_interval_minutes=60,
                 max_posts_per_day=10, exclude_dates_json=json.dumps(kw.get("exclude", [])), is_paused=False,
                 randomize_within_window=kw.get("random", True))
    rules = [ScheduleRule(window_start=a, window_end=b) for a, b in kw.get("windows", [("11:00", "13:00"), ("16:00", "18:00"), ("20:00", "22:00")])]
    return s, rules


def test_three_posts_three_windows_randomized_and_stable():
    s, rules = _schedule()
    service = ScheduleService()
    day = date(2026, 3, 10)
    a, b = service.slots_for_day(s, rules, day), service.slots_for_day(s, rules, day)
    assert a == b and len(a) == 3  # deterministic per day
    hours = [x.hour for x in a]
    assert 11 <= hours[0] < 13 and 16 <= hours[1] < 18 and 20 <= hours[2] < 22


def test_dst_spring_forward_and_fall_back():
    service = ScheduleService()
    s, rules = _schedule(tz="Europe/Berlin", n=1, random=False, windows=[("02:30", "02:30")])
    # 2026-03-29: 02:00 -> 03:00 in Berlin; 02:30 doesn't exist -> lands at 03:30 CEST = 01:30 UTC
    spring = service.slots_for_day(s, rules, date(2026, 3, 29))[0]
    assert spring == datetime(2026, 3, 29, 1, 30, tzinfo=UTC)
    # 2026-10-25: 02:30 happens twice; first occurrence (CEST) = 00:30 UTC
    autumn = service.slots_for_day(s, rules, date(2026, 10, 25))[0]
    assert autumn == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


def test_excluded_dates_and_pause():
    service = ScheduleService()
    s, rules = _schedule(exclude=["2026-03-10"])
    assert service.slots_for_day(s, rules, date(2026, 3, 10)) == []
    s.is_paused = True
    assert service.slots_for_day(s, rules, date(2026, 3, 11)) == []


def test_next_free_slot_skips_occupied():
    service = ScheduleService()
    s, rules = _schedule(n=2, random=False, windows=[("10:00", "10:00"), ("15:00", "15:00")])
    after = datetime(2026, 3, 10, 0, 0, tzinfo=UTC)
    first = service.next_free_slot(s, rules, after=after, occupied=[])
    assert first == datetime(2026, 3, 10, 10, 0, tzinfo=UTC)
    second = service.next_free_slot(s, rules, after=after, occupied=[first])
    assert second == datetime(2026, 3, 10, 15, 0, tzinfo=UTC)


@pytest.mark.asyncio
async def test_schedule_api_queue_calendar_and_drag(client):
    ws, base, _, cs = await _setup(client)
    sched = (await client.post(f"{base}/schedules", json={
        "name": "Daily", "channel_set_id": cs["id"], "timezone": "Europe/Moscow", "posts_per_day": 2,
        "windows": [{"start": "11:00", "end": "13:00"}, {"start": "18:00", "end": "20:00"}], "randomize": False,
    })).json()
    assert len(sched["next_slots"]) == 5
    bad = await client.post(f"{base}/schedules", json={"name": "x", "windows": [{"start": "10:00", "end": "12:00"},
                                                                              {"start": "11:00", "end": "13:00"}]})
    assert bad.status_code == 422

    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/approve")
    r = await client.post(f"{base}/content/{item['id']}/schedule", json={"schedule_id": sched["id"]})
    assert r.status_code == 200, r.text
    slot1 = r.json()["scheduled_at"]
    item2 = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item2['id']}/approve")
    slot2 = (await client.post(f"{base}/content/{item2['id']}/schedule", json={"schedule_id": sched["id"]})).json()["scheduled_at"]
    assert slot1 != slot2  # queue takes the next free slot

    start = datetime.now(UTC)
    cal = (await client.get(f"{base}/content/calendar", params={"start": start.isoformat(),
                                                                  "end": (start + timedelta(days=7)).isoformat()})).json()
    assert {e["id"] for e in cal["entries"]} == {item["id"], item2["id"]}
    assert cal["free_slots"] and all(s["at"] not in (slot1, slot2) for s in cal["free_slots"])

    new_time = (start + timedelta(days=3)).replace(microsecond=0)
    moved = await client.patch(f"{base}/content/{item['id']}/schedule", json={"scheduled_at": new_time.isoformat()})
    assert moved.status_code == 200
    assert datetime.fromisoformat(moved.json()["scheduled_at"]) == new_time
    past = await client.patch(f"{base}/content/{item['id']}/schedule",
                              json={"scheduled_at": (start - timedelta(hours=2)).isoformat()})
    assert past.status_code == 422


@pytest.mark.asyncio
async def test_misfire_reschedule_does_not_fire_everything(client, session_factory):
    ws, base, _, cs = await _setup(client)
    ids = []
    for _ in range(4):
        item = await _generate(client, base, cs["id"])
        await client.post(f"{base}/content/{item['id']}/approve")
        await client.post(f"{base}/content/{item['id']}/schedule", json={"scheduled_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()})
        ids.append(item["id"])
    async with session_factory() as s:  # scheduler "was down" for 2 hours
        for i, cid in enumerate(ids):
            (await s.get(ContentItem, uuid.UUID(cid))).scheduled_at = datetime.now(UTC) - timedelta(hours=2, minutes=i)
        await s.commit()
    result = await scheduler.tick()
    assert result["misfired"] == 4 and result["promoted"] == 0
    async with session_factory() as s:
        times = sorted(c.scheduled_at for c in (await s.execute(select(ContentItem))).scalars().all())
        assert all(scheduler._aware(t) > datetime.now(UTC) for t in times)
        gaps = [(b - a).total_seconds() for a, b in pairwise(times)]
        assert all(g >= 3600 - 1 for g in gaps)  # staggered, not a burst
    audit = (await client.get(f"{base}/audit", params={"action": "content"})).json()
    assert sum(1 for a in audit["items"] if a["action"] == "content.misfire_reschedule_next_slot") == 4


@pytest.mark.asyncio
async def test_misfire_skip_policy(client, session_factory):
    ws, base, _, cs = await _setup(client)
    s = (await client.get(f"{base}/settings")).json()["general"]
    await client.put(f"{base}/settings/general", json={**{k: s[k] for k in ("timezone", "misfire_grace_minutes", "cta_defaults")},
                                                      "workspace_name": "X", "misfire_policy": "SKIP"})
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/approve")
    await client.post(f"{base}/content/{item['id']}/schedule", json={"scheduled_at": (datetime.now(UTC) + timedelta(minutes=5)).isoformat()})
    async with session_factory() as sess:
        (await sess.get(ContentItem, uuid.UUID(item["id"]))).scheduled_at = datetime.now(UTC) - timedelta(hours=3)
        await sess.commit()
    await scheduler.tick()
    after = (await client.get(f"{base}/content/{item['id']}")).json()
    assert after["status"] == "APPROVED" and after["scheduled_at"] is None


# ------------------------------------------------------------------ P3 knowledge, P4 tone


TG_EXPORT = {
    "name": "Talos News", "type": "public_channel", "id": 1234,
    "messages": [
        {"id": 10, "type": "message", "date": "2023-01-05T10:00:00", "text": "Наш офис: ул. Старая, 1. Цена курса 10 000 ₽",
         "text_entities": [{"type": "plain", "text": "Наш офис"}]},
        {"id": 11, "type": "message", "date": "2023-02-01T10:00:00", "photo": "photos/1.jpg", "width": 800, "height": 600,
         "text": [{"type": "bold", "text": "Курс"}, " по CTR стартует"], "text_entities": [{"type": "bold", "text": "Курс"}]},
        {"id": 12, "type": "service", "date": "2023-02-02T10:00:00", "action": "pin_message"},
    ],
}


@pytest.mark.asyncio
async def test_telegram_export_import_preserves_metadata(client):
    ws, base, _, _ = await _setup(client)
    r = await client.post(f"{base}/knowledge/documents/upload",
                          files={"file": ("result.json", json.dumps(TG_EXPORT, ensure_ascii=False).encode(), "application/json")})
    assert r.status_code == 201, r.text
    doc = r.json()
    assert doc["kind"] == "HISTORICAL_POST" and doc["format"] == "telegram_export" and doc["entries"] == 2
    first = doc["preview"][0]["metadata"]
    assert first["message_id"] == 10 and first["date"] == "2023-01-05T10:00:00"
    assert first["source_channel"]["name"] == "Talos News"
    assert doc["preview"][1]["metadata"]["media"]["photo"] is True
    assert doc["preview"][1]["metadata"]["entities"][0]["type"] == "bold"
    assert any("service" in w for w in doc["warnings"])


@pytest.mark.asyncio
async def test_knowledge_formats_and_errors(client):
    ws, base, _, _ = await _setup(client)
    up = lambda name, data, kind="FACT": client.post(
        f"{base}/knowledge/documents/upload", files={"file": (name, data)}, data={"kind": kind})
    assert (await up("facts.md", b"# Contacts\n- HR: @talos_hr\n- Site: talos.example")).status_code == 201
    csv = b"kind,text,updated_at\nFACT,Price is 15000,2026-01-01\nRULE,Never promise income,2026-01-01\n"
    r = await up("facts.csv", csv)
    assert r.status_code == 201 and {e["kind"] for e in r.json()["preview"]} == {"FACT", "RULE"}
    assert (await up("x.exe", b"MZ")).status_code == 422
    assert (await up("bad.json", b"{oops")).status_code == 422
    assert (await up("fake.pdf", b"not a pdf")).status_code == 422
    hits = (await client.get(f"{base}/knowledge/search", params={"q": "15000"})).json()
    assert hits and hits[0]["kind"] == "FACT"


@pytest.mark.asyncio
async def test_current_facts_outrank_old_posts_in_prompt(client, session_factory):
    from app.services.content.context import PromptContextBuilder

    ws, base, _, _ = await _setup(client)
    await client.post(f"{base}/knowledge/documents/upload",
                      files={"file": ("result.json", json.dumps(TG_EXPORT, ensure_ascii=False).encode())})
    await client.post(f"{base}/knowledge/documents", json={"title": "Price", "kind": "FACT", "text": "Цена курса 15 000 ₽"})
    expired = (await client.post(f"{base}/knowledge/documents", json={
        "title": "Old promo", "kind": "FACT", "text": "Скидка 90% на курс",
        "valid_until": (datetime.now(UTC) - timedelta(days=1)).isoformat()})).json()
    disabled = (await client.post(f"{base}/knowledge/documents", json={"title": "Off", "kind": "FACT", "text": "Секретный факт курса"})).json()
    await client.patch(f"{base}/knowledge/documents/{disabled['id']}", json={"enabled": False})

    async with session_factory() as s:
        text, _ = await PromptContextBuilder(s).knowledge(uuid.UUID(ws), "цена курса")
    facts_pos = text.index("AUTHORITATIVE FACTS")
    hist_pos = text.index("HISTORICAL POSTS")
    assert facts_pos < hist_pos and "15 000" in text[facts_pos:hist_pos]
    assert "10 000" in text[hist_pos:] and "may be outdated" in text
    assert "Скидка 90%" not in text and "Секретный" not in text
    assert expired["id"]


@pytest.mark.asyncio
async def test_tone_precedence_series_channel_workspace(client, session_factory):
    from app.services.content.context import PromptContextBuilder

    ws, base, channels, cs = await _setup(client)
    mk = lambda name: client.post(f"{base}/tone-profiles", json={"name": name, "forbidden_vocabulary": ["синергия"]})
    t_ws, t_ch, t_series = [(await mk(n)).json() for n in ("WS", "Channel", "Series")]
    await client.post(f"{base}/tone-profiles/{t_ws['id']}/make-default")
    item = await _generate(client, base, cs["id"])

    async def source():
        async with session_factory() as s:
            profile, src = await PromptContextBuilder(s).resolve_tone(await s.get(ContentItem, uuid.UUID(item["id"])))
            return profile.name if profile else None, src

    assert await source() == ("WS", "workspace")
    for c in channels:
        await client.patch(f"{base}/channels/{c['id']}", json={"tone_profile_id": t_ch["id"]})
    assert await source() == ("Channel", "channel")
    await client.patch(f"{base}/channels/{channels[0]['id']}", json={"clear_tone_profile": True})
    assert await source() == ("WS", "workspace")  # channels disagree -> fall back
    series = (await client.post(f"{base}/series", json={"title": "S", "status": "ACTIVE", "tone_profile_id": t_series["id"]})).json()
    async with session_factory() as s:
        (await s.get(ContentItem, uuid.UUID(item["id"]))).series_id = uuid.UUID(series["id"])
        await s.commit()
    assert await source() == ("Series", "series")
    ctx = (await client.get(f"{base}/content/{item['id']}/context")).json()
    assert ctx["tone"]["source"] == "series"

    # Change Tone with an explicit profile
    r = await client.post(f"{base}/content/{item['id']}/transform", json={"operation": "change_tone", "tone_profile_id": t_ch["id"]})
    assert (await client.get(f"{base}/jobs/{r.json()['id']}")).json()["status"] == "SUCCESS"
    assert await source() == ("Channel", "explicit")


# ------------------------------------------------------------------ P5 series, P6 sources/ideas


@pytest.mark.asyncio
async def test_series_numbering_topics_and_no_repeats(client):
    ws, base, _, cs = await _setup(client)
    series = (await client.post(f"{base}/series", json={
        "title": "Media Buying Basics", "status": "ACTIVE", "channel_set_id": cs["id"], "category": "educational",
        "planned_topics": ["CTR", "CR", "CPA", "ROI"]})).json()
    assert series["next_label"] == "#001" and series["next_topic"] == "CTR"
    first = (await client.post(f"{base}/content/generate", json={"series_id": series["id"]})).json()["content"]
    assert first["topic"] == "CTR" and first["series_id"] == series["id"] and first["channel_set_id"] == cs["id"]
    s2 = (await client.get(f"{base}/series/{series['id']}")).json()
    assert s2["next_label"] == "#002" and s2["next_topic"] == "CR" and s2["in_progress"][0]["label"] == "#001"

    await client.post(f"{base}/content/{first['id']}/submit")
    assert (await client.post(f"{base}/content/{first['id']}/reject")).status_code == 200  # frees number + topic
    s3 = (await client.get(f"{base}/series/{series['id']}")).json()
    assert s3["next_label"] == "#001" and s3["next_topic"] == "CTR"

    await client.put(f"{base}/series/{series['id']}", json={**{k: s3[k] for k in ("title", "planned_topics", "channel_set_id")}, "status": "PAUSED"})
    assert (await client.post(f"{base}/content/generate", json={"series_id": series["id"]})).status_code == 409
    bad = await client.post(f"{base}/series", json={"title": "x", "numbering_format": "{oops}"})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_series_context_lists_previous_parts(client, session_factory):
    from app.services.content.context import PromptContextBuilder

    ws, base, _, cs = await _setup(client)
    series = (await client.post(f"{base}/series", json={"title": "Basics", "status": "ACTIVE", "channel_set_id": cs["id"],
                                                         "planned_topics": ["CTR", "CR"]})).json()
    first = (await client.post(f"{base}/content/generate", json={"series_id": series["id"]})).json()["content"]
    async with session_factory() as s:
        item = await s.get(ContentItem, uuid.UUID(first["id"]))
        item.status = ContentStatus.PUBLISHED
        await s.commit()
    second = (await client.post(f"{base}/content/generate", json={"series_id": series["id"]})).json()["content"]
    async with session_factory() as s:
        ctx = await PromptContextBuilder(s).series(await s.get(ContentItem, uuid.UUID(second["id"])))
    assert "part #002" in ctx and "do NOT repeat" in ctx and "#001" in ctx
    assert "This part's topic: CR" in ctx


@pytest.mark.asyncio
async def test_sources_ideas_flow_without_auto_generation(client, session_factory):
    ws, base, _, cs = await _setup(client)
    accounts = (await client.get(f"{base}/telegram/accounts")).json()
    src = (await client.post(f"{base}/sources", json={"kind": "telegram", "name": "Competitor",
                                                       "config": {"channel": "@rival", "account_id": accounts[0]["id"]}})).json()
    assert src["items_new"] == 3 and src["last_error"] is None
    async with session_factory() as s:
        assert (await s.execute(select(ContentItem))).scalars().first() is None  # fetch never generates posts
    ideas = (await client.get(f"{base}/ideas")).json()
    assert ideas["counts"]["NEW"] == 3 and ideas["items"][0]["url"].startswith("https://t.me/rival/")
    idea = ideas["items"][0]
    await client.patch(f"{base}/ideas/{idea['id']}", json={"status": "SHORTLISTED"})
    gen = (await client.post(f"{base}/content/generate", json={"source_item_id": idea["id"], "channel_set_id": cs["id"]})).json()
    assert gen["content"]["source_item_id"] == idea["id"]
    ideas = (await client.get(f"{base}/ideas", params={"status": "USED"})).json()
    assert [i["id"] for i in ideas["items"]] == [idea["id"]]
    again = (await client.post(f"{base}/sources/{src['id']}/fetch")).json()
    assert again["status"] == "SUCCESS"
    assert (await client.get(f"{base}/ideas")).json()["counts"]["NEW"] == 2  # no duplicates


@pytest.mark.asyncio
async def test_source_rejects_private_urls(client):
    ws, base, _, _ = await _setup(client)
    for url in ("http://127.0.0.1/feed", "http://169.254.169.254/latest", "file:///etc/passwd"):
        r = await client.post(f"{base}/sources", json={"kind": "rss", "name": "x", "config": {"url": url}})
        assert r.status_code == 422, url


# ------------------------------------------------------------------ P8 audit, P9 settings, P11 notifications, P14 costs


@pytest.mark.asyncio
async def test_audit_log_records_and_filters_without_secrets(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/approve")
    await client.post("/api/v1/auth/login", json={"email": "p@example.com", "password": "wrong-pass"})
    page = (await client.get(f"{base}/audit")).json()
    actions = {a["action"] for a in page["items"]}
    assert {"workspace.created", "telegram.account_connected", "telegram.channels_imported", "channel_set.created",
            "content.generation_requested", "content.generated", "content.approved", "auth.login_failed"} <= actions
    only = (await client.get(f"{base}/audit", params={"action": "content"})).json()
    assert only["items"] and all(a["action"].startswith("content.") for a in only["items"])
    raw = json.dumps(page)
    assert "wrong-pass" not in raw and "+15551112233" not in raw


@pytest.mark.asyncio
async def test_settings_mask_secrets_and_update_budget(client, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "timeweb_agent_api_key", "tw-secret-key-1234abcd")
    monkeypatch.setattr(get_settings(), "telegram_api_hash", "very-secret-hash")
    ws, base, _, _ = await _setup(client)
    s = (await client.get(f"{base}/settings")).json()
    assert s["ai"]["agent_api_key"] == "••••••••abcd"
    assert "3dce…5d5d" not in s["ai"]["agent_base_url"] or "…" in s["ai"]["agent_base_url"]
    raw = json.dumps(s)
    assert "tw-secret-key" not in raw and "very-secret-hash" not in raw and "3dce7cc5-7e2d" not in raw
    assert s["telegram"]["api_hash_configured"] is True
    r = await client.put(f"{base}/settings/budget", json={"daily_budget_rub": "5", "monthly_budget_rub": "100",
                                                         "max_cost_per_post_rub": "2", "budget_warning_pct": 70})
    assert r.json()["budget"]["daily_budget_rub"].startswith("5")


@pytest.mark.asyncio
async def test_budget_exhausted_blocks_generation_and_notifies(client):
    ws, base, _, cs = await _setup(client)
    await _generate(client, base, cs["id"])
    await client.put(f"{base}/settings/budget", json={"daily_budget_rub": "0.0001", "monthly_budget_rub": "100",
                                                     "max_cost_per_post_rub": "2", "budget_warning_pct": 80})
    r = await client.post(f"{base}/content/generate", json={"instruction": "x", "channel_set_id": cs["id"]})
    assert r.status_code == 402 and "daily budget reached" in r.json()["detail"]
    items = (await client.get(f"{base}/content")).json()["items"]
    r = await client.post(f"{base}/content/{items[0]['id']}/transform", json={"operation": "shorten"})
    assert r.status_code == 402


@pytest.mark.asyncio
async def test_notifications_unread_and_mark_read(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/submit")
    page = (await client.get(f"{base}/notifications")).json()
    assert page["unread"] >= 1 and page["items"][0]["kind"] == "approval.required"
    await client.post(f"{base}/notifications/{page['items'][0]['id']}/read")
    assert (await client.get(f"{base}/notifications")).json()["unread"] == page["unread"] - 1
    await client.post(f"{base}/notifications/read-all")
    assert (await client.get(f"{base}/notifications")).json()["unread"] == 0


@pytest.mark.asyncio
async def test_cost_dashboard_breakdown_and_dashboard(client):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/transform", json={"operation": "expand"})
    rejected = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{rejected['id']}/submit")
    assert (await client.post(f"{base}/content/{rejected['id']}/reject")).status_code == 200
    costs = (await client.get(f"{base}/analytics/costs")).json()
    by_key = {b["key"]: b for b in costs["breakdown"]}
    assert by_key["generation"]["requests"] == 1 and by_key["transforms"]["requests"] == 1
    assert by_key["rejected"]["requests"] == 1
    assert costs["input_tokens_month"] > 0 and len(costs["daily"]) == 30 and costs["top_content"]
    dash = (await client.get(f"{base}/analytics/dashboard")).json()
    assert dash["channels"] == 5 and dash["accounts_connected"] == 1
    assert dash["has_metrics"] is False and len(dash["views_7d"]) == 7


@pytest.mark.asyncio
async def test_command_palette_search(client):
    ws, base, _, cs = await _setup(client)
    await _generate(client, base, cs["id"])
    hits = (await client.get(f"{base}/search", params={"q": "ctr"})).json()
    assert any(h["kind"] == "post" for h in hits)
    assert any(h["kind"] == "channel_set" for h in (await client.get(f"{base}/search", params={"q": "net"})).json())
    assert any(h["kind"] == "channel" for h in (await client.get(f"{base}/search", params={"q": "fake channel"})).json())


@pytest.mark.asyncio
async def test_members_and_role_changes(client):
    ws, base, _, _ = await _setup(client)
    other = await client.post("/api/v1/auth/register", json={"email": "m@example.com", "password": "supersecret123", "workspace_name": "M"})
    assert other.status_code == 201
    await client.post("/api/v1/auth/login", json={"email": "p@example.com", "password": "supersecret123"})
    r = await client.post(f"/api/v1/workspaces/{ws}/members", json={"email": "m@example.com", "role": "EDITOR"})
    assert r.status_code == 201 and len(r.json()) == 2
    me = (await client.get("/api/v1/auth/me")).json()
    demote = await client.patch(f"/api/v1/workspaces/{ws}/members/{me['id']}", json={"role": "ADMIN"})
    assert demote.status_code == 409  # last owner


@pytest.mark.asyncio
async def test_image_generation_unavailable_is_explicit(client, monkeypatch):
    from app.services.ai import factory
    from app.services.ai.timeweb_provider import TimewebGatewayImageProvider

    ws, base, _, _ = await _setup(client)
    monkeypatch.setattr(factory, "get_image_provider", lambda: TimewebGatewayImageProvider())
    import app.api.v1.media as media_api

    monkeypatch.setattr(media_api, "get_image_provider", lambda: TimewebGatewayImageProvider())
    status = (await client.get(f"{base}/media/image-provider")).json()
    assert status["available"] is False and "does not expose image generation" in status["message"]
    r = await client.post(f"{base}/media/generate", json={"prompt": "a chart"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_fake_image_generation_creates_media_and_cost(client, monkeypatch):
    ws, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])

    async def no_s3(self, data, *, mime_type, workspace_id, prefix="media", ext=None):
        return "bucket", f"{prefix}/{workspace_id}/x.png", "0" * 64

    from app.services.media.storage import MediaStorage

    monkeypatch.setattr(MediaStorage, "put_object", no_s3)
    r = await client.post(f"{base}/media/generate", json={"prompt": "chart", "content_id": item["id"]})
    assert r.status_code == 202
    assert (await client.get(f"{base}/jobs/{r.json()['id']}")).json()["status"] == "SUCCESS"
    after = (await client.get(f"{base}/content/{item['id']}")).json()
    assert after["media_asset_id"]
    media = (await client.get(f"{base}/media", params={"tab": "generated"})).json()["items"]
    assert media[0]["source"] == "generated" and media[0]["used"] is True
    detail = (await client.get(f"{base}/media/{media[0]['id']}")).json()
    assert detail["prompt"] == "chart" and detail["linked_posts"][0]["id"] == item["id"]
    costs = (await client.get(f"{base}/content/{item['id']}/costs")).json()
    assert any(line["operation"] == "GENERATE_IMAGE" for line in costs["lines"])


@pytest.mark.asyncio
async def test_full_publish_partial_failure_and_retry(client, redis_client):
    from app.services.telegram.fake_provider import FAIL_ENTITIES_KEY

    ws, base, channels, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/approve")
    await client.put(f"{base}/dev/fake-telegram/failures", json={"entity_ids": [1004, 1005]})
    await client.post(f"{base}/content/{item['id']}/publish-now")
    await scheduler.tick()
    batch = (await client.get(f"{base}/distributions", params={"content_id": item["id"]})).json()[0]
    assert batch["status"] == "PARTIAL_FAILURE"
    ok_before = {p["id"]: p["telegram_message_id"] for p in batch["publications"] if p["status"] == "SUCCESS"}
    assert len(ok_before) == 3
    assert (await client.get(f"{base}/content/{item['id']}")).json()["status"] == "PARTIALLY_PUBLISHED"

    await redis_client.delete(FAIL_ENTITIES_KEY)
    retried = (await client.post(f"{base}/distributions/{batch['id']}/retry-failed")).json()
    assert retried["status"] == "SUCCESS"
    ok_after = {p["id"]: p["telegram_message_id"] for p in retried["publications"]}
    for pid, msg in ok_before.items():
        assert ok_after[pid] == msg  # succeeded publications untouched
    assert (await client.get(f"{base}/content/{item['id']}")).json()["status"] == "PUBLISHED"
    notes = (await client.get(f"{base}/notifications")).json()["items"]
    kinds = [n["kind"] for n in notes]
    assert "post.partially_published" in kinds and "post.published" in kinds
    list_item = (await client.get(f"{base}/content")).json()["items"][0]
    assert list_item["targets"] == 5 and list_item["published_count"] == 5


def test_dev_failure_endpoint_is_gated_on_fake_provider_and_non_production():
    from pathlib import Path

    from app.api.v1 import router as router_module

    assert "_settings.use_fake_telegram_provider and not _settings.is_production" in Path(router_module.__file__).read_text()


async def test_transform_revokes_existing_approval(client):
    _, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/submit")
    await client.post(f"{base}/content/{item['id']}/approve")
    r = await client.post(f"{base}/content/{item['id']}/transform", json={"operation": "shorten"})
    assert r.status_code == 202
    after = (await client.get(f"{base}/content/{item['id']}")).json()
    assert after["status"] == "PENDING_APPROVAL"


async def test_target_change_revokes_approval_and_can_clear_nullable_fields(client):
    _, base, _, cs = await _setup(client)
    item = await _generate(client, base, cs["id"])
    await client.post(f"{base}/content/{item['id']}/submit")
    await client.post(f"{base}/content/{item['id']}/approve")
    r = await client.patch(f"{base}/content/{item['id']}", json={"channel_set_id": None})
    assert r.status_code == 200, r.text
    assert r.json()["channel_set_id"] is None
    assert r.json()["status"] == "PENDING_APPROVAL"
