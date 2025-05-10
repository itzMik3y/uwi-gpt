'use client';
import Image from 'next/image';
import {
  Wrapper,
  Inner,
  Header,
  BannerCtn,
  Edges,
  Edge,
  Title,
  BriefNote,
} from './styles';
import MaskText from '@/app/components/Common/MaskText';
import { useIsMobile } from '../../../../lib/useIsMobile';
import {
  desktopBriefNotePhrase,
  mobileBriefNotePhrase,
} from './constants';

const ArtificalFreedom = () => {
  const isMobile = useIsMobile();

  return (
    <Wrapper>
      <BriefNote>
        {isMobile ? (
          <MaskText phrases={mobileBriefNotePhrase} tag="p" />
        ) : (
          <MaskText phrases={desktopBriefNotePhrase} tag="p" />
        )}
      </BriefNote>
    </Wrapper>
  );
};

export default ArtificalFreedom;
