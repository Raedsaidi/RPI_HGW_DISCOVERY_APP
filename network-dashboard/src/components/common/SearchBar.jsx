import React from 'react'
import { Search, X } from 'lucide-react'
import './SearchBar.css'

const SearchBar = ({
  value,
  onChange,
  placeholder = 'Search...',
  onClear,
  width = 280,
}) => {
  return (
    <div className="search-bar" style={{ width }}>
      <Search size={15} className="search-bar__icon" />
      <input
        className="search-bar__input"
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
      />
      {value && (
        <button
          className="search-bar__clear"
          onClick={() => {
            onChange('')
            onClear?.()
          }}
        >
          <X size={13} />
        </button>
      )}
    </div>
  )
}

export default SearchBar