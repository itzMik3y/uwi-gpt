import Layout from '@/src/components/Layout';
import '@/src/app/globals.css';
import type { Metadata } from 'next';
import { Inter, Roboto_Mono } from "next/font/google";

export const metadata: Metadata = {
  title: 'UWI-GPT',
  description: 'Everything you need to know about your Academic Journey',
};
const geistSans = Inter({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Roboto_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body  className={`${geistSans.variable} ${geistMono.variable} antialiased`}>
        <Layout>{children}</Layout>
      </body>
    </html>
  );
}
