'use client';
import Image from 'next/image';
import uwi_youths from '../../../../public/computer_lab.png';
import featured_mobile_banner from '../../../../public/images/featured_mobile_banner.png';
import { Wrapper, Inner, ImageContainer, Div } from './styles';
import RevealCover from '@/app/components/Common/RevealCover';
import { useIsMobile } from '../../../../lib/useIsMobile';
export const imageVariants = {
  hidden: {
    scale: 1.6,
  },
  visible: {
    scale: 1,
    transition: {
      duration: 1.4,
      ease: [0.6, 0.05, -0.01, 0.9],
      delay: 0.2,
    },
  },
};

const Featured = () => {
  const isMobile = useIsMobile();
  return (
    <Wrapper>
      <Inner>
        <ImageContainer>
          <RevealCover />
          <Div
            variants={imageVariants}
            initial="hidden"
            whileInView="visible"
            viewport={{ amount: 0.25, once: true }}
          >
            {isMobile ? (
              <Image
                src={featured_mobile_banner}
                alt="featured_mobile_banner"
                fill
              />
            ) : (
              <Image src={uwi_youths} alt="uwi computer lab" fill />
            )}
          </Div>
        </ImageContainer>
      </Inner>
    </Wrapper>
  );
};

export default Featured;
