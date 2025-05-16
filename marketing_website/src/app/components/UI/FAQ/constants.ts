type FAQItem = {
  question: string;
  answer: string;
};

export const desktopHeaderPhrase = ['Frequently asked', 'questions'];
export const mobileHeaderPhrase = ['Frequently', 'asked', 'questions'];
export const animate = {
  initial: {
    y: '100%',
    opacity: 0,
  },
  open: (i: number) => ({
    y: '0%',
    opacity: 1,
    transition: { duration: 1, delay: 0.1 * i, ease: [0.33, 1, 0.68, 1] },
  }),
};

export const faqData: FAQItem[] = [
  {
    question: 'What is UWI-GPT and how does it work?',
    answer:
      'UWI-GPT is a conversational AI platform designed for UWI students. It uses a chat-based interface built with React, powered by a FastAPI backend and a PostgreSQL database, to assist with academic advising and access to UWI-related resources.',
  },
  {
    question: 'What technologies power UWI-GPT?',
    answer:
      'UWI-GPT uses a modern stack: React for the front-end, FastAPI for backend services, PostgreSQL for session management, and an embedded Quran semantic search vector space to support intelligent responses. It also incorporates advanced NLP techniques like Retrieval-Augmented Generation (RAG), BM25, and MMR reranking.',
  },
  {
    question: 'How is my data handled when using UWI-GPT?',
    answer:
      'Student credentials are used solely to access necessary university systems and are never stored. UWI-GPT is designed to comply with UWI’s security and privacy standards.',
  },
];