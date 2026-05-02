import React from 'react'
import './Spinner.css'

const Spinner = ({ size = 'md', centered = false, text }) => {
  const el = (
    <div className={`spinner spinner--${size}`}>
      <div className="spinner__circle" />
      {text && <span className="spinner__text">{text}</span>}
    </div>
  )

  if (centered) {
    return <div className="spinner-centered">{el}</div>
  }

  return el
}

export default Spinner