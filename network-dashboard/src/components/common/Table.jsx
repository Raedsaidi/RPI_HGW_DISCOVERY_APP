import React from 'react'
import './Table.css'

const Table = ({
  columns = [],
  data = [],
  loading = false,
  emptyText = 'No data found',
  rowKey = 'id',
}) => {
  if (loading) {
    return (
      <div className="table-wrap">
        <table className="table">
          <thead>
            <tr>
              {columns.map((col) => (
                <th key={col.key} style={{ width: col.width }}>
                  {col.title}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: 6 }).map((_, i) => (
              <tr key={i} className="table__skeleton-row">
                {columns.map((col) => (
                  <td key={col.key}>
                    <div className="table__skeleton-cell" />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {columns.map((col) => (
              <th
                key={col.key}
                style={{
                  width: col.width,
                  textAlign: col.align || 'left',
                }}
              >
                {col.title}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="table__empty">
                <div className="table__empty-content">
                  <span className="table__empty-icon">📭</span>
                  <span>{emptyText}</span>
                </div>
              </td>
            </tr>
          ) : (
            data.map((row, idx) => (
              <tr key={row[rowKey] ?? idx} className="table__row">
                {columns.map((col) => (
                  <td
                    key={col.key}
                    style={{ textAlign: col.align || 'left' }}
                  >
                    {col.render
                      ? col.render(row[col.key], row)
                      : row[col.key] ?? (
                          <span className="table__null">—</span>
                        )}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}

export default Table