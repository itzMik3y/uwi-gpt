'use client';

import Link from 'next/link';

export default function Navbar() {
  return (
    <nav className="w-full py-6 px-8 flex justify-between items-center shadow">
      <Link href="/" className="text-xl font-bold">UWI-GPT</Link>
      <div className="flex gap-6 text-sm sm:text-base">
        <Link href="/features">Features</Link>
        <Link href="/pricing">Pricing</Link>
        <Link href="/contact">Contact</Link>
      </div>
    </nav>
  );
}