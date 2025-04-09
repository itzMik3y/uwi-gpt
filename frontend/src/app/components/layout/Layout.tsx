// components/layout/Layout.tsx
"use client"

import { ReactNode } from "react";
import { Header } from "@/app/components/layout/Header";
import { Sidebar } from "@/app/components/layout/Sidebar";
import { Footer } from "@/app/components/layout/Footer";
import { motion, AnimatePresence } from "framer-motion";
import { usePathname } from "next/navigation";

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  const pathname = usePathname();
  
  return (
    <div className="flex min-h-screen flex-col">
      <Header />
      
      <div className="flex flex-1">
        <Sidebar />
        <AnimatePresence mode="wait">
          <motion.main 
            key={pathname}
            className="flex-1"
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ 
              type: "spring", 
              stiffness: 260, 
              damping: 20,
              duration: 0.3 
            }}
          >
            {children}
          </motion.main>
        </AnimatePresence>
      </div>
      
      <Footer />
    </div>
  );
}