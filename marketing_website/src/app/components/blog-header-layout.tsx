"use client";

import MaxWidthWrapper from "@/src/app/components/max-width-wrapper";

export function BlogHeaderLayout() {
  return (
    <MaxWidthWrapper className="py-6 md:pb-8 md:pt-10">
      <div className="max-w-screen-sm">
        <h1 className="font-heading text-3xl md:text-4xl">Blog</h1>
        <p className="mt-3.5 text-base text-muted-foreground md:text-lg">
          Catch Up on the extensive features of UWI-GPT and the benefits it brings to you.
        </p>
      </div>
    </MaxWidthWrapper>
  );
}