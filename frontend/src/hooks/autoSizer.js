import { useState, useLayoutEffect, useRef, useCallback } from 'react';

function autoSizer(value) {
  const ref = useRef(null);
  const [borderWidth, setBorderWidth] = useState(0);

  useLayoutEffect(() => {
    const style = window.getComputedStyle(ref.current);
    const currentBorderWidth = parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);

    if (currentBorderWidth !== borderWidth) {
      setBorderWidth(currentBorderWidth);
    }

    const currentHeight = ref.current.scrollHeight + currentBorderWidth;
    if (ref.current.style.height !== `${currentHeight}px`) {
      ref.current.style.height = `${currentHeight}px`;
    }
  }, [value, borderWidth]);

  return ref;
}

export default autoSizer;