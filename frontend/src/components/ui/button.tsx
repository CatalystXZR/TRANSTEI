import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 rounded-lg border border-transparent bg-clip-padding font-medium whitespace-nowrap select-none transition-[background-color,border-color,color,box-shadow,transform] duration-150 ease-out outline-none hover:-translate-y-px active:translate-y-0 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-45 aria-invalid:border-critico [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-[18px]",
  {
    variants: {
      variant: {
        default:
          "bg-marca text-white shadow-elev-1 hover:bg-marca-hover hover:shadow-elev-2",
        outline:
          "border-borde-fuerte bg-superficie text-tinta hover:border-marca/40 hover:bg-marca-tenue hover:text-marca",
        secondary:
          "bg-superficie-hundida text-tinta hover:bg-marca-tenue hover:text-marca",
        ghost: "text-tinta-2 hover:bg-superficie-hundida hover:text-tinta",
        destructive:
          "bg-critico-tenue text-critico hover:bg-critico hover:text-white",
        success: "bg-ok text-white shadow-elev-1 hover:bg-ok/90 hover:shadow-elev-2",
        link: "text-marca underline-offset-4 hover:translate-y-0 hover:underline",
      },
      size: {
        default: "h-11 px-4 text-base",
        xs: "h-8 gap-1 px-2.5 text-sm [&_svg:not([class*='size-'])]:size-3.5",
        sm: "h-9 px-3 text-[15px] [&_svg:not([class*='size-'])]:size-4",
        lg: "h-12 px-5 text-[17px]",
        icon: "size-10",
        "icon-xs": "size-8 [&_svg:not([class*='size-'])]:size-3.5",
        "icon-sm": "size-9 [&_svg:not([class*='size-'])]:size-4",
        "icon-lg": "size-12",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  )
}

export { Button, buttonVariants }
