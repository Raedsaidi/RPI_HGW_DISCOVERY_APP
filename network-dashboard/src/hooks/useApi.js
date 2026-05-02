import { useState, useEffect, useCallback, useRef } from 'react'

const useApi = (apiFn, params = {}, options = {}) => {
  const {
    immediate = true,
    deps = [],
  } = options

  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(immediate)
  const [error, setError] = useState(null)

  const paramsRef = useRef(params)
  paramsRef.current = params

  const execute = useCallback(
    async (overrideParams) => {
      setLoading(true)
      setError(null)
      try {
        const res = await apiFn(overrideParams ?? paramsRef.current)
        setData(res.data)
        return res.data
      } catch (err) {
        const msg =
          err.response?.data?.detail ||
          err.message ||
          'An error occurred'
        setError(msg)
        return null
      } finally {
        setLoading(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    deps
  )

  useEffect(() => {
    if (immediate) {
      execute()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [immediate, ...deps])

  return { data, loading, error, execute, setData }
}

export default useApi