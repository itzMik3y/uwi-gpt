// components/ui/loading-screen.tsx
"use client";

import { Loader2 } from "lucide-react";

export default function LoadingScreen() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-blue-100">
      <div className="flex flex-col items-center space-y-4 text-center">
        <Loader2 className="h-12 w-12 animate-spin text-red-600" />
        <h1 className="text-2xl font-bold text-gray-900">Loading UWI-GPT</h1>
        <p className="text-gray-600">Please wait while we prepare your academic companion</p>
      </div>
    </div>
  );
}