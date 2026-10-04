import { describe, expect, it } from "vitest";
import {
  editorToTelegram,
  plainText,
  sanitizeTelegramHtml,
  telegramToEditor,
} from "./telegramHtml";

describe("editorToTelegram", () => {
  it("turns paragraphs into lines and keeps inline formatting", () => {
    const html =
      '<p><strong>Title</strong></p><p></p><p>Body with <em>italic</em> and <a href="https://x.io">link</a></p>';
    expect(editorToTelegram(html)).toBe(
      '<b>Title</b>\n\nBody with <i>italic</i> and <a href="https://x.io">link</a>',
    );
  });

  it("renders lists as bullet / numbered lines", () => {
    const html =
      "<ul><li><p>one</p></li><li><p>two</p></li></ul><ol><li><p>a</p></li><li><p>b</p></li></ol>";
    expect(editorToTelegram(html)).toBe("• one\n• two\n1. a\n2. b");
  });

  it("keeps blockquote and pre, escapes text", () => {
    const html =
      "<blockquote><p>quote 1</p><p>quote 2</p></blockquote><pre><code>a < b && c</code></pre>";
    expect(editorToTelegram(html)).toBe(
      "<blockquote>quote 1\nquote 2</blockquote>\n<pre>a &lt; b &amp;&amp; c</pre>",
    );
  });

  it("drops unsafe links but keeps their text", () => {
    expect(
      editorToTelegram('<p><a href="javascript:alert(1)">click</a></p>'),
    ).toBe("click");
  });
});

describe("telegramToEditor", () => {
  it("round-trips formatted posts", () => {
    const tg =
      "<b>5 tips</b>\n\nIntro line\n• first\n• second\n1. step\n2. next\n<blockquote>note</blockquote>\nEnd <code>x</code>";
    expect(editorToTelegram(telegramToEditor(tg))).toBe(tg);
  });

  it("produces paragraphs and lists", () => {
    expect(telegramToEditor("a\n• b")).toBe(
      "<p>a</p><ul><li><p>b</p></li></ul>",
    );
  });
});

describe("sanitizeTelegramHtml (preview XSS guard)", () => {
  it("strips scripts, images, event handlers and unsafe hrefs", () => {
    const evil =
      '<b onclick="x()">ok</b><img src=x onerror=alert(1)><script>alert(2)</script><a href="javascript:x">l</a><iframe src="//e"></iframe>';
    const out = sanitizeTelegramHtml(evil);
    expect(out).toBe("<b>ok</b>alert(2)l");
    expect(out).not.toMatch(/onerror|onclick|<script|<img|<iframe|javascript:/);
  });

  it("escapes text that looks like markup", () => {
    expect(sanitizeTelegramHtml("&lt;script&gt;")).toBe("&lt;script&gt;");
  });

  it("extracts plain text", () => {
    expect(plainText("<b>Hi</b> <i>there</i>")).toBe("Hi there");
  });
});
