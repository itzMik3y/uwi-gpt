// components/layout/HorizontalNav.tsx
"use client"

import Link from "next/link"
import { usePathname } from "next/navigation"
import { 
  Home, 
  LayoutDashboard, 
  Users, 
  User, 
  Settings 
} from "lucide-react"

export function HorizontalNav() {
  const pathname = usePathname()
  
  const navItems = [
    {
      label: "Home",
      path: "/dashboard",
      icon: <Home className="mr-2 h-5 w-5" />,
    },
    {
      label: "Dashboards",
      path: "/dashboards",
      icon: <LayoutDashboard className="mr-2 h-5 w-5" />,
    },
    {
      label: "Segments",
      path: "/segments",
      icon: <Users className="mr-2 h-5 w-5" />,
    },
    {
      label: "Account",
      path: "/account",
      icon: <User className="mr-2 h-5 w-5" />,
    },
    {
      label: "Settings",
      path: "/settings",
      icon: <Settings className="mr-2 h-5 w-5" />,
    },
  ]
  
  return (
    <div className="mx-auto my-4 flex rounded-lg bg-white p-1 shadow-md">
      {navItems.map((item) => {
        const isActive = pathname === item.path || pathname.startsWith(item.path + "/")
        
        return (
          <Link
            key={item.path}
            href={item.path}
            className={`
              flex flex-1 items-center justify-center rounded-lg px-3 py-2 text-sm transition-colors md:text-base
              ${isActive
                ? "bg-blue-600 text-white"
                : "text-gray-700 hover:bg-blue-50 hover:text-blue-600"
              }
            `}
          >
            {item.icon}
            <span>{item.label}</span>
          </Link>
        )
      })}
    </div>
  )
}