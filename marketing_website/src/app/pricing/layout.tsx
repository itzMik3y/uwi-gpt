import type { Metadata } from "next"
import { Inter } from "next/font/google"
import "@/src/app/globals.css"
import { ThemeProvider } from "@/src/components/theme-provider"
import { ModeToggle } from "@/src/components/theme-toggler"
import { Header } from "@/src/components"
import Footer from "@/src/components/ui/Footer/index"

const inter = Inter({ subsets: ["latin"] })

export const metadata: Metadata = {
  title: "Pricing Page",
  description: "Pricing page for a SaaS product using Shadcn UI",
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning={true}>
      
      <body className={inter.className}>
        <Header/>
        <ThemeProvider attribute="class" defaultTheme="dark" enableSystem disableTransitionOnChange>
          {children}
        </ThemeProvider>
        <Footer/>
      </body>
    </html>
  )
}
