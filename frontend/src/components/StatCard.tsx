import React from 'react';

interface StatCardProps {
  label: string;
  value: number | string;
  subtext?: string;
  variant?: 'default' | 'success' | 'warning' | 'error';
}

export const StatCard: React.FC<StatCardProps> = ({
  label,
  value,
  subtext,
  variant = 'default',
}) => {
  let borderStyle = 'border-borderMuted bg-white';
  let valueColor = 'text-charcoal-900';

  if (variant === 'success') {
    borderStyle = 'border-sage-200 bg-sage-50/40';
    valueColor = 'text-sage-800';
  } else if (variant === 'warning') {
    borderStyle = 'border-amber-200 bg-amber-50/30';
    valueColor = 'text-amber-900';
  } else if (variant === 'error') {
    borderStyle = 'border-red-200 bg-red-50/30';
    valueColor = 'text-red-800';
  }

  return (
    <div className={`p-5 rounded-lg border ${borderStyle} transition-colors`}>
      <div className="text-xs font-medium uppercase tracking-wider text-charcoal-500 mb-1">
        {label}
      </div>
      <div className={`text-3xl font-semibold tracking-tight ${valueColor}`}>
        {value}
      </div>
      {subtext && (
        <div className="text-xs text-charcoal-400 mt-1">{subtext}</div>
      )}
    </div>
  );
};
