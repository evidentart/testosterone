import type { HTMLAttributes, ReactNode } from "react";

export interface CardProps extends Omit<HTMLAttributes<HTMLDivElement>, "title"> {
  title?: ReactNode;
  actions?: ReactNode;
}

export function Card({ title, actions, className, children, ...props }: CardProps) {
  return (
    <div
      className={`glass-card p-5 ${className ?? ""}`}
      {...props}
    >
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {title ? <h3 className="text-base font-bold text-white">{title}</h3> : <span />}
          {actions}
        </div>
      )}
      {children}
    </div>
  );
}
