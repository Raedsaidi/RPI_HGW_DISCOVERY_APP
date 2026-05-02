import React from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import './Pagination.css'

const Pagination = ({ page, totalPages, total, pageSize, onChange }) => {
  const start = (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, total)

  const pages = []
  const delta = 2

  for (let i = 1; i <= totalPages; i++) {
    if (
      i === 1 ||
      i === totalPages ||
      (i >= page - delta && i <= page + delta)
    ) {
      pages.push(i)
    } else if (
      i === page - delta - 1 ||
      i === page + delta + 1
    ) {
      pages.push('...')
    }
  }

  // deduplicate ellipsis
  const dedupedPages = pages.filter(
    (p, idx) => !(p === '...' && pages[idx - 1] === '...')
  )

  return (
    <div className="pagination">
      <span className="pagination__info">
        Showing <strong>{start}–{end}</strong> of <strong>{total}</strong>
      </span>

      <div className="pagination__controls">
        <button
          className="pagination__btn"
          disabled={page <= 1}
          onClick={() => onChange(page - 1)}
        >
          <ChevronLeft size={15} />
        </button>

        {dedupedPages.map((p, idx) =>
          p === '...' ? (
            <span key={`dots-${idx}`} className="pagination__dots">
              ···
            </span>
          ) : (
            <button
              key={p}
              className={`pagination__btn ${
                p === page ? 'pagination__btn--active' : ''
              }`}
              onClick={() => onChange(p)}
            >
              {p}
            </button>
          )
        )}

        <button
          className="pagination__btn"
          disabled={page >= totalPages}
          onClick={() => onChange(page + 1)}
        >
          <ChevronRight size={15} />
        </button>
      </div>
    </div>
  )
}

export default Pagination