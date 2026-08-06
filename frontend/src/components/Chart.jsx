// Dependency-free SVG charts for the analytics dashboard.
import React from 'react'

export function BarChart({ data, xKey, yKey, height = 160, color = 'var(--accent)', label }) {
  if (!data?.length) return <div className="muted">No data</div>
  const max = Math.max(...data.map(d => d[yKey]), 1)
  const barW = 100 / data.length
  return (
    <div className="chart">
      {label && <div className="chart-label">{label}</div>}
      <svg viewBox={`0 0 100 ${height / 4}`} preserveAspectRatio="none"
        style={{ width: '100%', height }}>
        {data.map((d, i) => {
          const h = (d[yKey] / max) * (height / 4 - 4)
          return (
            <rect key={i} x={i * barW + barW * 0.15} y={height / 4 - h}
              width={barW * 0.7} height={h} rx="0.5" fill={color}>
              <title>{`${d[xKey]}: ${d[yKey]}`}</title>
            </rect>
          )
        })}
      </svg>
      <div className="chart-axis">
        <span>{data[0][xKey]}</span>
        <span>{data[data.length - 1][xKey]}</span>
      </div>
    </div>
  )
}

export function HBarList({ data, labelKey, valueKey, format, color = 'var(--accent-2)' }) {
  if (!data?.length) return <div className="muted">No data</div>
  const max = Math.max(...data.map(d => d[valueKey]), 1)
  return (
    <div className="hbar-list">
      {data.map((d, i) => (
        <div key={i} className="hbar-row">
          <span className="hbar-label" title={d[labelKey]}>{d[labelKey]}</span>
          <div className="hbar-track">
            <div className="hbar-fill" style={{ width: `${(d[valueKey] / max) * 100}%`, background: color }} />
          </div>
          <span className="hbar-value">{format ? format(d[valueKey]) : d[valueKey]}</span>
        </div>
      ))}
    </div>
  )
}
