import * as React from 'react';
import { Slot } from '@radix-ui/react-slot';
import { cva, type VariantProps } from 'class-variance-authority';
import { cn } from '../../lib/utils';

const variants = cva(
  'inline-flex items-center justify-center gap-2 rounded-md px-3 py-2 text-sm font-medium disabled:opacity-50 disabled:pointer-events-none',
  {
    variants: {
      variant: {
        default: 'bg-[var(--accent)] text-white',
        outline: 'border border-[var(--border)] bg-[var(--surface)]',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof variants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, asChild = false, ...props }, ref) => {
    const Component = asChild ? Slot : 'button';

    return (
      <Component
        className={cn(variants({ variant }), className)}
        ref={ref}
        {...props}
      />
    );
  },
);

Button.displayName = 'Button';