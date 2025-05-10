import Link from "next/link";

export default function Footer() {
  return (
    <footer className="w-full border-t mt-20 px-6 py-10 text-sm text-gray-500 bg-white dark:bg-black dark:text-gray-400">
      <div className="w-full max-w-7xl mx-auto flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div className="text-center sm:text-left">
          © {new Date().getFullYear()} UWI-GPT. All rights reserved.
        </div>
        <div className="flex justify-center sm:justify-end gap-6">
          <Link href="/features" className="hover:underline">
            Features
          </Link>
          <Link href="/pricing" className="hover:underline">
            Pricing
          </Link>
          <Link href="/contact" className="hover:underline">
            Contact
          </Link>
        </div>
      </div>
    </footer>
  );
}