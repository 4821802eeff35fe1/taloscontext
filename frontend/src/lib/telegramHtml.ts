/**
 * Telegram HTML <-> rich-editor HTML.
 *
 * Telegram's HTML parse mode has no paragraphs or lists: text is plain lines
 * with inline tags (b, i, u, s, a, code, pre, blockquote). The editor (TipTap)
 * works with <p>/<ul>/<ol>. Lists are stored as "• item" / "1. item" lines.
 *
 * Every function here rebuilds output from an allow-list, so whatever goes in,
 * only safe markup comes out — the preview never renders raw input.
 */

const INLINE: Record<string, string> = {
  B: "b",
  STRONG: "b",
  I: "i",
  EM: "i",
  U: "u",
  INS: "u",
  S: "s",
  STRIKE: "s",
  DEL: "s",
  CODE: "code",
};
const SAFE_HREF = /^(https?:\/\/|tg:\/\/|mailto:)/i;

export function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function escapeAttr(text: string): string {
  return escapeHtml(text).replace(/"/g, "&quot;");
}

function parse(html: string): HTMLElement {
  const doc = new DOMParser().parseFromString(
    `<div>${html}</div>`,
    "text/html",
  );
  return doc.body.firstElementChild as HTMLElement;
}

/** Inline content -> Telegram inline markup (allow-listed). */
function inline(node: Node): string {
  if (node.nodeType === Node.TEXT_NODE)
    return escapeHtml(node.textContent ?? "");
  if (node.nodeType !== Node.ELEMENT_NODE) return "";
  const el = node as HTMLElement;
  const inner = Array.from(el.childNodes).map(inline).join("");
  if (el.tagName === "BR") return "\n";
  if (el.tagName === "A") {
    const href = el.getAttribute("href") ?? "";
    return SAFE_HREF.test(href)
      ? `<a href="${escapeAttr(href)}">${inner}</a>`
      : inner;
  }
  const tag = INLINE[el.tagName];
  return tag && inner ? `<${tag}>${inner}</${tag}>` : inner;
}

/** Editor HTML (p/ul/ol/blockquote/pre + inline) -> Telegram HTML. */
export function editorToTelegram(editorHtml: string): string {
  const root = parse(editorHtml);
  const lines: string[] = [];
  const blocks = (parent: Element, into: string[]) => {
    for (const node of Array.from(parent.childNodes)) {
      if (node.nodeType === Node.TEXT_NODE) {
        if ((node.textContent ?? "").trim())
          into.push(escapeHtml(node.textContent ?? ""));
        continue;
      }
      if (node.nodeType !== Node.ELEMENT_NODE) continue;
      const el = node as HTMLElement;
      switch (el.tagName) {
        case "P":
        case "H1":
        case "H2":
        case "H3":
          into.push(inline(el));
          break;
        case "UL":
          Array.from(el.children).forEach((li) =>
            into.push(`• ${inline(firstBlock(li))}`),
          );
          break;
        case "OL": {
          const start = Number(el.getAttribute("start") ?? "1");
          Array.from(el.children).forEach((li, i) =>
            into.push(`${start + i}. ${inline(firstBlock(li))}`),
          );
          break;
        }
        case "BLOCKQUOTE": {
          const inner: string[] = [];
          blocks(el, inner);
          into.push(`<blockquote>${inner.join("\n")}</blockquote>`);
          break;
        }
        case "PRE":
          into.push(`<pre>${escapeHtml(el.textContent ?? "")}</pre>`);
          break;
        default:
          into.push(inline(el));
      }
    }
  };
  blocks(root, lines);
  return lines
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function firstBlock(li: Element): Element {
  return (li.querySelector(":scope > p") as Element) ?? li;
}

const BULLET = /^(?:•|-|–)\s+/;
const NUMBERED = /^(\d+)[.)]\s+/;

/** Telegram HTML -> editor HTML (lines become paragraphs/lists). */
export function telegramToEditor(telegramHtml: string): string {
  const safe = sanitizeTelegramHtml(telegramHtml);
  // Split on newlines that are outside <pre>/<blockquote> blocks.
  const parts = safe.split(
    /(<pre>[\s\S]*?<\/pre>|<blockquote>[\s\S]*?<\/blockquote>)/,
  );
  const out: string[] = [];
  let list: { type: "ul" | "ol"; items: string[]; start: number } | null = null;
  const flush = () => {
    if (!list) return;
    const start =
      list.type === "ol" && list.start !== 1 ? ` start="${list.start}"` : "";
    out.push(
      `<${list.type}${start}>${list.items.map((i) => `<li><p>${i}</p></li>`).join("")}</${list.type}>`,
    );
    list = null;
  };
  for (const part of parts) {
    if (!part) continue;
    if (part.startsWith("<pre>")) {
      flush();
      out.push(part);
      continue;
    }
    if (part.startsWith("<blockquote>")) {
      flush();
      const inner = part
        .slice(12, -13)
        .split("\n")
        .map((l) => `<p>${l}</p>`)
        .join("");
      out.push(`<blockquote>${inner}</blockquote>`);
      continue;
    }
    const lines = part.split("\n");
    lines.forEach((line, idx) => {
      // Text around a block element continues the same visual line.
      if (
        (idx === 0 && part !== parts[0] && line === "") ||
        (idx === lines.length - 1 && line === "" && idx !== 0)
      )
        return;
      const bullet = line.match(BULLET);
      const numbered = line.match(NUMBERED);
      if (bullet) {
        if (list?.type !== "ul") flush();
        list = list ?? { type: "ul", items: [], start: 1 };
        list.items.push(line.slice(bullet[0].length));
      } else if (numbered) {
        if (list?.type !== "ol") flush();
        list = list ?? { type: "ol", items: [], start: Number(numbered[1]) };
        list.items.push(line.slice(numbered[0].length));
      } else {
        flush();
        out.push(`<p>${line}</p>`);
      }
    });
  }
  flush();
  return out.join("");
}

/** Rebuilds Telegram HTML keeping only Telegram-supported tags and safe links. */
export function sanitizeTelegramHtml(html: string): string {
  const root = parse(html);
  const walk = (node: Node): string => {
    if (node.nodeType === Node.TEXT_NODE)
      return escapeHtml(node.textContent ?? "");
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const el = node as HTMLElement;
    const inner = Array.from(el.childNodes).map(walk).join("");
    if (el.tagName === "BR") return "\n";
    if (el.tagName === "A") {
      const href = el.getAttribute("href") ?? "";
      return SAFE_HREF.test(href)
        ? `<a href="${escapeAttr(href)}">${inner}</a>`
        : inner;
    }
    if (el.tagName === "PRE")
      return `<pre>${escapeHtml(el.textContent ?? "")}</pre>`;
    if (el.tagName === "BLOCKQUOTE") return `<blockquote>${inner}</blockquote>`;
    const tag = INLINE[el.tagName];
    return tag ? `<${tag}>${inner}</${tag}>` : inner; // drops script/img/iframe/on* etc.
  };
  return Array.from(root.childNodes).map(walk).join("");
}

export function plainText(telegramHtml: string): string {
  return parse(telegramHtml).textContent ?? "";
}

/** Telegram limits: 4096 chars for a text message, 1024 for a media caption. */
export function lengthLimit(hasMedia: boolean) {
  return hasMedia ? 1024 : 4096;
}
