// components/layout/Sidebar.tsx
"use client"

import { useState } from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import { 
  Home, 
  LayoutDashboard, 
  Users, 
  User, 
  Settings,
  ChevronLeft,
  ChevronRight,
  Menu
} from "lucide-react"
import { Button } from "@/components/ui/button"

interface NavItem {
  path: string
  label: string
  icon: React.ReactNode
  submenu?: { label: string; path: string }[]
}

export function Sidebar() {
  const pathname = usePathname()
  const [collapsed, setCollapsed] = useState(false)
  const [openSubmenu, setOpenSubmenu] = useState<string | null>(null)
  
  const navItems: NavItem[] = [
    {
      path: "/dashboard",
      label: "Home",
      icon: <Home className="h-5 w-5" />,
    },
    {
      path: "/dashboards",
      label: "Dashboards",
      icon: <LayoutDashboard className="h-5 w-5" />,
      submenu: [
        { label: "Option 1", path: "/dashboards/option1" },
        { label: "Option 2", path: "/dashboards/option2" },
      ]
    },
    {
      path: "/segments",
      label: "Segments",
      icon: <Users className="h-5 w-5" />,
      submenu: [
        { label: "Option 1", path: "/segments/option1" },
        { label: "Option 2", path: "/segments/option2" },
      ]
    },
    {
      path: "/account",
      label: "Account",
      icon: <User className="h-5 w-5" />,
      submenu: [
        { label: "Option 1", path: "/account/option1" },
        { label: "Option 2", path: "/account/option2" },
      ]
    },
    {
      path: "/settings",
      label: "Settings",
      icon: <Settings className="h-5 w-5" />,
      submenu: [
        { label: "Option 1", path: "/settings/option1" },
        { label: "Option 2", path: "/settings/option2" },
        { label: "Option 3", path: "/settings/option3" },
        { label: "Option 4", path: "/settings/option4" },
      ]
    },
  ]

  const toggleSidebar = () => {
    setCollapsed(!collapsed)
    if (collapsed) {
      setOpenSubmenu(null)
    }
  }

  const toggleSubmenu = (label: string) => {
    setOpenSubmenu(openSubmenu === label ? null : label)
  }

  return (
    <aside 
      className={`
        relative h-full border-r bg-white transition-all duration-300 ease-in-out
        ${collapsed ? 'w-16' : 'w-64'}
      `}
    >
      <Button 
        variant="ghost" 
        size="icon" 
        className="absolute -right-3 top-4 z-10 flex h-6 w-6 items-center justify-center rounded-full border border-gray-200 bg-white shadow-sm hover:bg-gray-100"
        onClick={toggleSidebar}
        aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
      >
        {collapsed ? <ChevronRight className="h-4 w-4" /> : <ChevronLeft className="h-4 w-4" />}
      </Button>
      
      <nav className="flex flex-col p-2">
        {navItems.map((item) => {
          const isActive = pathname === item.path || pathname.startsWith(item.path + "/")
          const isSubmenuOpen = openSubmenu === item.label && !collapsed
          
          return (
            <div key={item.path} className="mb-1">
              <div
                className={`
                  group flex cursor-pointer items-center justify-between rounded-lg p-3 transition-colors
                  ${isActive
                    ? "bg-blue-600 text-white"
                    : "text-gray-700 hover:bg-blue-50 hover:text-blue-600"
                  }
                `}
                onClick={() => item.submenu && !collapsed && toggleSubmenu(item.label)}
              >
                <Link
                  href={item.path}
                  className="flex items-center gap-3"
                  title={collapsed ? item.label : undefined}
                  onClick={(e) => item.submenu && !collapsed && e.preventDefault()}
                >
                  <span className="flex-shrink-0">{item.icon}</span>
                  <span className={`truncate transition-opacity duration-300 ${collapsed ? 'opacity-0 invisible w-0' : 'opacity-100 visible'}`}>
                    {item.label}
                  </span>
                </Link>
                
                {item.submenu && !collapsed && (
                  <ChevronRight 
                    className={`h-4 w-4 transition-transform ${isSubmenuOpen ? "rotate-90" : ""}`} 
                  />
                )}
              </div>
              
              {/* Submenu */}
              {item.submenu && isSubmenuOpen && (
                <div className="ml-8 mt-1 space-y-1">
                  {item.submenu.map((subItem) => {
                    const isSubActive = pathname === subItem.path
                    
                    return (
                      <Link
                        key={subItem.path}
                        href={subItem.path}
                        className={`
                          block rounded-md px-3 py-2 text-sm transition-colors
                          ${isSubActive
                            ? "bg-blue-50 text-blue-600 font-medium"
                            : "text-gray-600 hover:bg-blue-50 hover:text-blue-600"
                          }
                        `}
                      >
                        {subItem.label}
                      </Link>
                    )
                  })}
                </div>
              )}
            </div>
          )
        })}
      </nav>
      
      {/* Mobile toggle button */}
      <Button
        variant="ghost"
        size="icon"
        className="absolute left-4 top-4 z-10 block md:hidden"
        onClick={toggleSidebar}
      >
        <Menu className="h-5 w-5" />
      </Button>
    </aside>
  )
}