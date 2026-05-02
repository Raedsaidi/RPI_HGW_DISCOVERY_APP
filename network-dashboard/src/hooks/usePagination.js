import { useState, useCallback } from 'react'

const usePagination = (defaultPageSize = 25) => {
  const [page, setPage] = useState(1)
  const [pageSize] = useState(defaultPageSize)

  const reset = useCallback(() => setPage(1), [])

  const goTo = useCallback((p) => setPage(p), [])

  return { page, pageSize, goTo, reset }
}

export default usePagination