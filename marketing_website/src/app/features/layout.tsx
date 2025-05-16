import { BlogHeaderLayout } from "@/src/app/components/blog-header-layout";
import MaxWidthWrapper from "@/src/app/components/max-width-wrapper";

export default function BlogLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <>
      <BlogHeaderLayout />
      <MaxWidthWrapper className="pb-16">{children}</MaxWidthWrapper>
    </>
  );
}