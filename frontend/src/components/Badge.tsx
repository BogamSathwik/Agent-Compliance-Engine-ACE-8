import React from 'react';

interface BadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

export const Badge: React.FC<BadgeProps> = ({ status, size = 'md' }) => {
  const norm = (status || '').toUpperCase().trim();

  let styles = 'bg-charcoal-100 text-charcoal-700 border-charcoal-200';

  if (norm === 'READY_TO_PUBLISH' || norm === 'PUBLISHED' || norm === 'PASSED' || norm === 'PASS' || norm === 'RESOLVED') {
    styles = 'bg-sage-50 text-sage-800 border-sage-300 font-medium';
  } else if (norm === 'NOT_READY' || norm === 'FAILED' || norm === 'FAIL' || norm === 'PUBLICATION_FAILED' || norm === 'CRITICAL' || norm === 'HIGH') {
    styles = 'bg-red-50 text-red-800 border-red-200 font-medium';
  } else if (norm === 'QUEUED' || norm === 'RUNNING' || norm === 'PUBLICATION_REQUESTED' || norm === 'IN_PROGRESS' || norm === 'PENDING') {
    styles = 'bg-amber-50 text-amber-900 border-amber-200 font-medium';
  } else if (norm === 'UNVERIFIED' || norm === 'MEDIUM' || norm === 'LOW' || norm === 'PUBLICATION_STATUS_UNKNOWN' || norm === 'OPEN') {
    styles = 'bg-charcoal-50 text-charcoal-700 border-charcoal-300 font-medium';
  }

  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-xs';

  return (
    <span
      className={`inline-flex items-center rounded-md border tracking-wide uppercase font-semibold ${sizeClasses} ${styles}`}
    >
      {norm.replace(/_/g, ' ')}
    </span>
  );
};
