import Link from "next/link"
import { MessageSquare, Calendar, FileText, GraduationCap } from "lucide-react"
import { Card } from "@/components/ui/card"

export function QuickActions() {
  const actions = [
    { 
      icon: <MessageSquare className="mb-2 h-8 w-8 text-blue-500" />, 
      title: "Chat with Advisor", 
      href: "/chat" 
    },
    { 
      icon: <Calendar className="mb-2 h-8 w-8 text-blue-500" />, 
      title: "Schedule Meeting", 
      href: "/schedule" 
    },
    { 
      icon: <FileText className="mb-2 h-8 w-8 text-blue-500" />, 
      title: "View Reports", 
      href: "/reports" 
    },
    { 
      icon: <GraduationCap className="mb-2 h-8 w-8 text-blue-500" />, 
      title: "Academic Plan", 
      href: "/academic-plan" 
    },
  ]

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 p-4">
      {actions.map((action) => (
        <Link key={action.href} href={action.href}>
          <Card className="flex flex-col items-center p-4 text-center hover:shadow-md hover:bg-gray-50 cursor-pointer transition-all h-full">
            {action.icon}
            <p className="font-medium">{action.title}</p>
          </Card>
        </Link>
      ))}
    </div>
  )
}