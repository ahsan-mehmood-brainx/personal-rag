import type { CSSProperties } from 'react'
import styles from './Skeleton.module.css'

export function Skeleton({ width = '100%', height = 14, radius, style }: {
  width?: number | string
  height?: number | string
  radius?: number | string
  style?: CSSProperties
}) {
  return (
    <span
      className={styles.skeleton}
      style={{ width, height, borderRadius: radius, ...style }}
      aria-hidden="true"
    />
  )
}
