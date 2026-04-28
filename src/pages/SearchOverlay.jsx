import React, { useRef } from "react";
import Search from "components/search/Search";
import RestrictedSearch from "components/search/RestrictedSearch";
import { Transition } from "react-transition-group";
import { useConfig } from "hooks/config";

export default function SearchOverlay() {
  const ref = useRef();
  const { config } = useConfig();

  const defaultStyle = {
    left: 0,
    right: 0,
    top: 0,
    bottom: 0,
    position: "absolute",
    background: "rgba(0, 0, 0, 0)",
    overflowY: "scroll",
    zIndex: 1100,
    transition: "background 100ms ease-in-out",
  };

  const transitionStyles = {
    entering: { background: "rgba(0, 0, 0, 0)" },
    entered: { background: "rgba(0, 0, 0, 0.9)" },
  };

  // Use RestrictedSearch when library_restrict is enabled
  const SearchComponent = config?.libraryRestrict ? RestrictedSearch : Search;

  return (
    <Transition appear={false} in={true} timeout={100} nodeRef={ref}>
      {(state) => (
        <div
          style={{
            ...defaultStyle,
            ...transitionStyles[state],
          }}
          ref={ref}
        >
          <SearchComponent />
        </div>
      )}
    </Transition>
  );
}
