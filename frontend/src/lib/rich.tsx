import katex from "katex";
import { marked } from "marked";
import { useMemo, type MouseEvent } from "react";
import type { Citation } from "./api";

const escAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/**
 * Markdown + KaTeX math + citation chips, from untrusted model text.
 * Raw HTML in the source is escaped before markdown runs, so model output cannot inject markup.
 */
export function renderRich(text: string, cites: Citation[] = []): string {
  const stash: string[] = [];
  const keep = (html: string) => `\u0000${stash.push(html) - 1}\u0000`;
  const tex = (src: string, display: boolean) => keep(katex.renderToString(src, { displayMode: display, throwOnError: false, output: "html" }));
  let t = String(text || "")
    .replace(/\$\$([\s\S]+?)\$\$/g, (_, m) => tex(m, true))
    .replace(/\\\[([\s\S]+?)\\\]/g, (_, m) => tex(m, true))
    .replace(/\\\(([\s\S]+?)\\\)/g, (_, m) => tex(m, false))
    .replace(/(^|[^\\$])\$([^$\n]{1,200}?)\$/g, (_, pre, m) => pre + tex(m, false));
  t = t.replace(/</g, "&lt;");
  let html = marked.parse(t, { async: false, breaks: true, gfm: true }) as string;
  html = html.replace(/\u0000(\d+)\u0000/g, (_, i) => stash[Number(i)]);
  const byTag = new Map(cites.map((c) => [c.tag, c]));
  html = html.replace(/\[(S\d+)\]/g, (_, tag: string) => {
    const c = byTag.get(tag);
    return c ? `<button type="button" class="cite-chip" data-unit="${escAttr(c.unit_id)}" data-q="${escAttr(c.quote || "")}" title="${escAttr(c.label)}">${tag.slice(1)}</button>` : "";
  });
  for (const c of cites) {
    const lab = c.label.replace(/</g, "&lt;");
    html = html.split(`[${lab}]`).join(`<button type="button" class="cite-chip wide" data-unit="${escAttr(c.unit_id)}">${lab}</button>`);
  }
  return html;
}

export function Rich({
  text,
  cites,
  onCite,
  className,
}: {
  text: string;
  cites?: Citation[];
  onCite?: (unitId: string, quote: string) => void;
  className?: string;
}) {
  const html = useMemo(() => renderRich(text, cites), [text, cites]);
  const click = (e: MouseEvent<HTMLDivElement>) => {
    const el = (e.target as HTMLElement).closest<HTMLElement>("[data-unit]");
    if (el && onCite) onCite(el.dataset.unit!, el.dataset.q || "");
  };
  return <div className={`rich ${className ?? ""}`} onClick={click} dangerouslySetInnerHTML={{ __html: html }} />;
}
