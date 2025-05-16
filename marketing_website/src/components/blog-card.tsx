import Link from "next/link";
import { cn, formatDate, placeholderBlurhash } from "@/src/lib/utils";
import BlurImage from "@/src/components/blur-image";
import { Post } from "@/src/types/blog"; 

export function BlogCard({
  data,
  priority,
  horizontale = false,
}: {
  data: Post;
  priority?: boolean;
  horizontale?: boolean;
}) {
  return (
    <article
      className={`group relative ${
        horizontale ? "grid grid-cols-1 gap-3 md:grid-cols-2 md:gap-6" : "flex flex-col space-y-2"
      }`}
    >
      {data.image && (
        <div className="w-full overflow-hidden rounded-xl border">
          <img
            alt={data.title}
            src={data.image}
            className={horizontale ? "lg:h-72 object-cover object-center w-full" : "object-cover object-center w-full"}
            width={800}
            height={400}
            loading={priority ? "eager" : "lazy"}
          />
        </div>
      )}
      <div className={`flex flex-1 flex-col ${horizontale ? "justify-center" : "justify-between"}`}>
        <div className="w-full">
          <h2 className="my-1.5 line-clamp-2 font-heading text-2xl">{data.title}</h2>
          {data.description && <p className="line-clamp-2 text-muted-foreground">{data.description}</p>}
        </div>
        <div className="mt-4">
          {data.date && <p className="text-sm text-muted-foreground">{new Date(data.date).toLocaleDateString()}</p>}
        </div>
      </div>
      <Link href={data.slug} className="absolute inset-0">
        <span className="sr-only">View Article</span>
      </Link>
    </article>
  );
}