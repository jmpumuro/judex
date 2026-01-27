import { FC } from 'react'
import { Loader2 } from 'lucide-react'

interface SpinnerProps {
  size?: number
  className?: string
}

const Spinner: FC<SpinnerProps> = ({ size = 24, className = '' }) => {
  return (
    <div className={`flex items-center justify-center ${className}`}>
      <Loader2 className="animate-spin text-primary" size={size} />
    </div>
  )
}

export default Spinner
