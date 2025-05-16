import { BlogPosts } from "@/src/components/blog-post";

const rawPosts = [
  {
    _id: "Academic-Advising",
    title: "Academic Advising",
    description: "Personalized course selection, degree planning, and academic goal setting for new and final year student.",
    date: "2025-05-01",
    image: "/images/hand.jpg",
    published: true,
    slug: "/features",
  },
  {
    _id: "mental-health-tools",
    title: "Mental Health Tools for Students",
    description: "Access coping strategies and wellnes resources through the ai agents numerouse resources.",
    date: "2025-04-14",
    image: "/images/Machine.webp",
    published: true,
    slug: "/features",
  },
  {
    _id: "University-Guidance",
    title: "University Guidance",
    description: "Understand UWI's policies, resources, and procedures with ease.",
    date: "2025-04-14",
    image: "/images/current_students.png",
    published: true,
    slug: "/features",
  },
  {
    _id: "Scheduling-Features",
    title: "Sheduling Features",
    description: "Schedule appointments with unversity staff for personal or academic support.",
    date: "2025-04-14",
    image: "/images/arpita_orientation.jpg",
    published: true,
    slug: "/features",
  }
];

export default function BlogPage() {
  const posts = rawPosts
    .filter((post) => post.published)
    .sort((a, b) => b.date.localeCompare(a.date));

  return <BlogPosts posts={posts} />;
}