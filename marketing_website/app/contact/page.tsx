export default function ContactPage() {
    return (
      <section className="max-w-3xl mx-auto py-20 px-6">
        <h2 className="text-3xl sm:text-4xl font-bold mb-8 text-center">Contact Us</h2>
        <p className="text-gray-700 dark:text-gray-300 mb-6 text-center">
          Got questions, feedback, or partnership ideas? We’d love to hear from you.
        </p>
        <form className="space-y-6">
          <div>
            <label htmlFor="name" className="block mb-1 font-medium">Name</label>
            <input type="text" id="name" className="w-full border rounded px-4 py-2 dark:bg-gray-900" />
          </div>
          <div>
            <label htmlFor="email" className="block mb-1 font-medium">Email</label>
            <input type="email" id="email" className="w-full border rounded px-4 py-2 dark:bg-gray-900" />
          </div>
          <div>
            <label htmlFor="message" className="block mb-1 font-medium">Message</label>
            <textarea id="message" rows={4} className="w-full border rounded px-4 py-2 dark:bg-gray-900"></textarea>
          </div>
          <button
            type="submit"
            className="bg-black text-white dark:bg-white dark:text-black px-6 py-3 rounded-full font-medium hover:opacity-90 transition"
          >
            Send Message
          </button>
        </form>
      </section>
    );
  }