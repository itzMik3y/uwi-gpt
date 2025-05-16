import {
  FAQ,
  Featured,
  FinancilaFreedom,
  HeroSection,
  OffersSection,
} from '@/src/components';

export default function Home() {
  return (
    <main>
      <HeroSection />
      <Featured />
      <OffersSection />
      <FinancilaFreedom />
      <FAQ />
    </main>
  );
}
