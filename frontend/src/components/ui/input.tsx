import * as React from "react"
import { Input as InputPrimitive } from "@base-ui/react/input"
import { cn } from "cn"

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <InputPrimitive
      type={type}
      data-slot="input"
      className={cn(
        "h-11 w-full min-w-0 rounded-lg border border-borde-fuerte bg-superficie px-3 py-2 text-base text-tinta shadow-[inset_0_1px_0_rgb(23_21_31/0.03)] transition-[border-color,box-shadow,background-color] duration-150 outline-none file:mr-3 file:inline-flex file:h-8 file:cursor-pointer file:rounded-md file:border-0 file:bg-marca-tenue file:px-3 file:text-sm file:font-medium file:text-marca placeholder:text-tinta-3/70 hover:border-tinta-3/50 focus-visible:border-marca focus-visible:shadow-[0_0_0_4px_rgb(42_35_122/0.12)] focus-visible:outline-none disabled:pointer-events-none disabled:cursor-not-allowed disabled:bg-superficie-hundida disabled:opacity-60 aria-invalid:border-critico aria-invalid:bg-critico-tenue/40 aria-invalid:focus-visible:shadow-[0_0_0_4px_rgb(185_28_28/0.12)]",
        className
      )}
      {...props}
    />
  )
}

export { Input }
