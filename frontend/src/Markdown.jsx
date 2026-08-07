import React from 'react'

// Minimal, dependency-free Markdown renderer for AI answers.
//
// It builds REACT ELEMENTS, never HTML strings — so no answer can inject
// markup into the page, whatever the AI writes. Supports what answers
// actually use: headings, bold/italic/code, links, bullet and numbered
// lists, tables, block quotes, code blocks and horizontal rules.

const INLINE = [
  { re: /\*\*([^*]+)\*\*/, tag: 'strong' },
  { re: /__([^_]+)__/, tag: 'strong' },
  { re: /\*([^*\n]+)\*/, tag: 'em' },
  { re: /_([^_\n]+)_/, tag: 'em' },
  { re: /~~([^~]+)~~/, tag: 'del' },
  { re: /`([^`]+)`/, tag: 'code' },
]

const LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/
const BARE_URL_RE = /(https?:\/\/[^\s<>"')]+)/

function renderInline(text, keyPrefix = 'i') {
  if (!text) return null
  // links first (their label may itself contain bold/code)
  const link = LINK_RE.exec(text)
  if (link) {
    return [
      renderInline(text.slice(0, link.index), `${keyPrefix}a`),
      <a key={`${keyPrefix}l`} href={link[2]} target="_blank" rel="noreferrer noopener">
        {renderInline(link[1], `${keyPrefix}t`)}
      </a>,
      renderInline(text.slice(link.index + link[0].length), `${keyPrefix}b`),
    ]
  }
  for (const { re, tag } of INLINE) {
    const m = re.exec(text)
    if (!m) continue
    const Tag = tag
    return [
      renderInline(text.slice(0, m.index), `${keyPrefix}a`),
      <Tag key={`${keyPrefix}m`}>{tag === 'code' ? m[1] : renderInline(m[1], `${keyPrefix}c`)}</Tag>,
      renderInline(text.slice(m.index + m[0].length), `${keyPrefix}b`),
    ]
  }
  const url = BARE_URL_RE.exec(text)
  if (url) {
    return [
      text.slice(0, url.index),
      <a key={`${keyPrefix}u`} href={url[1]} target="_blank" rel="noreferrer noopener">{url[1]}</a>,
      renderInline(text.slice(url.index + url[0].length), `${keyPrefix}b`),
    ]
  }
  return text
}

const isTableRow = (line) => /^\s*\|.*\|\s*$/.test(line)
const isDivider = (line) => /^\s*\|?[\s:-]*-[\s|:-]*\|?\s*$/.test(line) && line.includes('-')
const cells = (line) => line.trim().replace(/^\||\|$/g, '').split('|').map(c => c.trim())

export default function Markdown({ text }) {
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n')
  const blocks = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]

    // fenced code block
    if (/^\s*```/.test(line)) {
      const body = []
      i++
      while (i < lines.length && !/^\s*```/.test(lines[i])) body.push(lines[i++])
      i++
      blocks.push(<pre key={blocks.length} className="md-code"><code>{body.join('\n')}</code></pre>)
      continue
    }

    // table (header row + divider + body)
    if (isTableRow(line) && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const head = cells(line)
      i += 2
      const rows = []
      while (i < lines.length && isTableRow(lines[i])) rows.push(cells(lines[i++]))
      blocks.push(
        <div key={blocks.length} className="table-scroll">
          <table className="md-table">
            <thead><tr>{head.map((c, x) => <th key={x}>{renderInline(c, `h${x}`)}</th>)}</tr></thead>
            <tbody>
              {rows.map((r, y) => (
                <tr key={y}>{r.map((c, x) => <td key={x}>{renderInline(c, `c${y}${x}`)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>
      )
      continue
    }

    // heading
    const heading = /^\s{0,3}(#{1,6})\s+(.*)$/.exec(line)
    if (heading) {
      const Tag = `h${Math.min(6, heading[1].length + 2)}`  // keep page hierarchy sane
      blocks.push(<Tag key={blocks.length} className="md-h">{renderInline(heading[2], `h${i}`)}</Tag>)
      i++
      continue
    }

    // horizontal rule
    if (/^\s{0,3}([-*_])\s*(\1\s*){2,}$/.test(line)) {
      blocks.push(<hr key={blocks.length} />)
      i++
      continue
    }

    // block quote
    if (/^\s{0,3}>\s?/.test(line)) {
      const body = []
      while (i < lines.length && /^\s{0,3}>\s?/.test(lines[i])) {
        body.push(lines[i++].replace(/^\s{0,3}>\s?/, ''))
      }
      blocks.push(
        <blockquote key={blocks.length} className="md-quote">
          {renderInline(body.join(' '), `q${i}`)}
        </blockquote>
      )
      continue
    }

    // lists (bullet or numbered)
    const bullet = /^\s*[-*+]\s+(.*)$/
    const numbered = /^\s*\d+[.)]\s+(.*)$/
    if (bullet.test(line) || numbered.test(line)) {
      const ordered = numbered.test(line)
      const re = ordered ? numbered : bullet
      const items = []
      while (i < lines.length && re.test(lines[i])) items.push(re.exec(lines[i++])[1])
      const Tag = ordered ? 'ol' : 'ul'
      blocks.push(
        <Tag key={blocks.length} className="md-list">
          {items.map((item, x) => <li key={x}>{renderInline(item, `li${x}`)}</li>)}
        </Tag>
      )
      continue
    }

    // blank line
    if (!line.trim()) { i++; continue }

    // paragraph (consecutive non-empty, non-special lines)
    const para = []
    while (i < lines.length && lines[i].trim()
           && !/^\s*```/.test(lines[i])
           && !/^\s{0,3}#{1,6}\s/.test(lines[i])
           && !/^\s{0,3}>\s?/.test(lines[i])
           && !bullet.test(lines[i]) && !numbered.test(lines[i])
           && !isTableRow(lines[i])) {
      para.push(lines[i++])
    }
    if (para.length) {
      blocks.push(<p key={blocks.length} className="md-p">{renderInline(para.join(' '), `p${i}`)}</p>)
    } else {
      i++  // a special line the loops above did not consume — never stall
    }
  }

  return <div className="markdown">{blocks}</div>
}

// Plain-text and HTML versions of an answer, for "copy with formatting".
export function toHtml(text) {
  const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
  const lines = String(text || '').split('\n')
  const out = []
  let list = null
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null } }
  for (const line of lines) {
    const inline = (s) => esc(s)
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\*([^*]+)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
    const heading = /^\s{0,3}(#{1,6})\s+(.*)$/.exec(line)
    const bullet = /^\s*[-*+]\s+(.*)$/.exec(line)
    const numbered = /^\s*\d+[.)]\s+(.*)$/.exec(line)
    if (heading) { closeList(); out.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`) }
    else if (bullet) { if (list !== 'ul') { closeList(); out.push('<ul>'); list = 'ul' } out.push(`<li>${inline(bullet[1])}</li>`) }
    else if (numbered) { if (list !== 'ol') { closeList(); out.push('<ol>'); list = 'ol' } out.push(`<li>${inline(numbered[1])}</li>`) }
    else if (!line.trim()) { closeList() }
    else { closeList(); out.push(`<p>${inline(line)}</p>`) }
  }
  closeList()
  return out.join('')
}
