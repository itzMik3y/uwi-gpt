import Image from 'next/image';
import uwi_footer from '../../../../public/uwi_gpt_logo.svg';
import qr_code from '../../../../public/svgs/qr_code.svg';
import ic_google_playstore from '../../../../public/svgs/ic_google_playstore.svg';
import ic_baseline_apple from '../../../../public/svgs/ic_baseline_apple.svg';
import ic_chevron_down from '../../../../public/svgs/ic_chevron_down.svg';
import ic_copyright from '../../../../public/svgs/ic_copyright.svg';
import Link from 'next/link';

const linksArr = [
  {
    title: '',
    links: [],
  },
  {
    title: '',
    links: [],
  },
  {
    title: 'More Info',
    links: [
      { label: 'Features', url: '/features' },
      { label: 'Pricing', url: '/pricing' },
      { label: 'Contact Us', url: '/contact' },
    ],
  },
];

import {
  Wrapper,
  Inner,
  FooterLogo,
  FooterMainContent,
  FooterMiddle,
  QRContainer,
  QRImageCtn,
  TextCtn,
  IconCtn,
  FooterNavigation,
  GridColumn,
  LinksContainer,
  FooterBottom,
  Translator,
  CopyRight,
} from './styles';

const Footer = () => {
  return (
    <Wrapper>
      <Inner>
        <FooterLogo>
          <Image src={uwi_footer} alt="uwi_footer" />
        </FooterLogo>
        <FooterMainContent>
          <FooterMiddle>
            <QRContainer>
              <QRImageCtn>
                <Image src={qr_code} alt="qr_code" />
              </QRImageCtn>
              <TextCtn>
                <p>Scan to download App on the Playstore and Appstore.</p>
                <IconCtn>
                  <Image src={ic_google_playstore} alt="playstore icon" />
                  <Image src={ic_baseline_apple} alt="apple icon" />
                </IconCtn>
              </TextCtn>
            </QRContainer>
            <FooterNavigation>
              {linksArr.map((group, i) => (
                <GridColumn key={i}>
                  <h3>{group.title}</h3>
                  <LinksContainer>
                    {group.links.map((link, j) => (
                      <li key={j}>
                        <Link href={link.url}>{link.label}</Link>
                      </li>
                    ))}
                  </LinksContainer>
                </GridColumn>
              ))}
            </FooterNavigation>
          </FooterMiddle>
          <FooterBottom>
            <Translator>
              <h3>English (United States)</h3>
              <Image src={ic_chevron_down} alt="chevron down" />
            </Translator>
            <CopyRight>
              <Image src={ic_copyright} alt="copyright svg" />
              UWI-GPT.
            </CopyRight>
          </FooterBottom>
        </FooterMainContent>
      </Inner>
    </Wrapper>
  );
};

export default Footer;
