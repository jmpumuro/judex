import { FC } from 'react'
import { Verdict, VideoStatus } from '@/types'

interface BadgeProps {
  variant: Verdict | VideoStatus
  children: React.ReactNode
  className?: string
}

const Badge: FC<BadgeProps> = ({ variant, children, className = '' }) => {
  const variantClasses: Record<string, string> = {
    SAFE: 'badge-success',
    CAUTION: 'badge-warning',
    UNSAFE: 'badge-danger',
    NEEDS_REVIEW: 'badge-info',
    pending: 'badge-warning',
    processing: 'badge-info',
    error: 'badge-danger',
    completed: 'badge-success',
  }

  return (
    <span className={`badge ${variantClasses[variant] || 'badge-info'} ${className}`}>
      {children}
    </span>
  )
}

export default Badge
