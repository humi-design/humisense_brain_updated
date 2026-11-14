/**
 * Skip link.
 *
 * Lets a keyboard user jump past the navigation straight to the content. It is
 * visually hidden until focused.
 */

export function SkipLink() {
  return (
    <a href="#hs-content" className="hs-skip-link">
      Skip to content
    </a>
  );
}
