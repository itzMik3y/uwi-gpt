'use client';

import Image from 'next/image';
import {
  Wrapper,
  Inner,
  LogoContainer,
  Nav,
  CallToActions,
  AbsoluteLinks,
  BurgerMenu,
} from './styles';
import uwi_logo from '../../../../public/uwi_gpt_logo.svg';
import ic_bars from '../../../../public/svgs/ic_bars.svg';
import AnimatedLink from '@/src/components/Common/AnimatedLink';
import { useState } from 'react';
import { motion } from 'framer-motion';
import { links, menu } from './constants';
import Link from 'next/link';

const Header = () => {
  const [isOpen, setIsOpen] = useState(false);
  return (
    <Wrapper>
      <Inner>
        <LogoContainer>
          <a href="/">
            <Image src={uwi_logo} alt="UWI logo" priority />
          </a>
          <BurgerMenu onClick={() => setIsOpen(!isOpen)}>
            <motion.div
              variants={menu}
              animate={isOpen ? 'open' : 'closed'}
              initial="closed"
            ></motion.div>
            <Image src={ic_bars} alt="bars" />
          </BurgerMenu>
        </LogoContainer>
        <Nav className={isOpen ? 'active' : ''}>
          {links.map((link, i) => (
            <AnimatedLink key={i} title={link.linkTo} href={link.url} />
          ))}
        </Nav>
        <div style={{ padding: '0.5rem 0.75rem', minWidth: '19rem' }} />
      </Inner>
    </Wrapper>
  );
};

export default Header;
