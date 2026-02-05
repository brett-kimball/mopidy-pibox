import { useEffect, useRef, useState } from "react";

/**
 * Hook to detect if text overflows its container
 * Returns a ref to attach to the element and a boolean indicating overflow
 */
export const useTextOverflow = (dependency) => {
  const ref = useRef(null);
  const [isOverflowing, setIsOverflowing] = useState(false);

  useEffect(() => {
    const checkOverflow = () => {
      if (ref.current) {
        const isOverflow = ref.current.scrollWidth > ref.current.clientWidth;
        setIsOverflowing(isOverflow);
      }
    };

    // Use requestAnimationFrame to ensure DOM is fully rendered
    requestAnimationFrame(() => {
      checkOverflow();
    });

    // Check again on window resize
    window.addEventListener("resize", checkOverflow);
    return () => window.removeEventListener("resize", checkOverflow);
  }, [dependency]);

  return { ref, isOverflowing };
};
