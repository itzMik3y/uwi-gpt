'use client';
import { Geist, Geist_Mono } from "next/font/google";  // Import font here
import { ReactLenis } from '@studio-freight/react-lenis';
import StyledComponentsRegistry from '../../../lib/registry';
import { GlobalStyles } from './GlobalStyles'; // Global Styles for this layout
import { Footer, Header, Preloader } from '..';
import { useState } from 'react';

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

const Layout = ({ children }: { children: React.ReactNode }) => {
  const [complete, setComplete] = useState(false);

  return (
    <StyledComponentsRegistry>
      <ReactLenis
        root
        easing={(t: number) => Math.min(1, 1.001 - Math.pow(2, -10 * t))} // Custom scroll easing
      >
        <GlobalStyles />
        <Preloader setComplete={setComplete} />
        <div className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
          {/* Only apply font styles here */}
          <Header />
          <main>{children}</main>
          <Footer />
        </div>
      </ReactLenis>
    </StyledComponentsRegistry>
  );
};

export default Layout;