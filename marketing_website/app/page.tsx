import {
  FAQ,
  Featured,
  FinancilaFreedom,
  HeroSection,
  OffersSection,
} from '@/app/components';

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
