/**
 * Compatibility shim: restores the global `JSX` namespace as an alias of `React.JSX`.
 *
 * `@types/react` 19 removed the global `JSX` namespace and scoped it to
 * `React.JSX`. This project compiles with `"jsx": "react-jsx"` (the automatic
 * runtime), so ~170 component files annotate their return type as
 * `JSX.Element` *without* importing `React`. Rewriting them to
 * `React.JSX.Element` would mean adding a `React` import to every one of those
 * files purely to satisfy a type annotation — a large diff that touches
 * unrelated components and buys nothing.
 *
 * Re-declaring the namespace globally is the migration path DefinitelyTyped
 * recommends for this case. Every member resolves to the identical `React.JSX`
 * type, so this is an alias and not a redefinition: no type is widened and no
 * runtime behaviour is affected. All members are mirrored, because omitting one
 * would silently make it unresolvable.
 *
 * Type aliases are used rather than `interface X extends ... {}` so the file
 * needs no lint suppressions. The trade-off is that the *global* namespace is
 * no longer declaration-mergeable — nothing in this repo or its dependencies
 * augments it, and libraries that add custom elements target
 * `React.JSX.IntrinsicElements` nowadays, which stays augmentable.
 */
import type * as React from 'react';

declare global {
  namespace JSX {
    type ElementType = React.JSX.ElementType;
    type Element = React.JSX.Element;
    type ElementClass = React.JSX.ElementClass;
    type ElementAttributesProperty = React.JSX.ElementAttributesProperty;
    type ElementChildrenAttribute = React.JSX.ElementChildrenAttribute;
    type LibraryManagedAttributes<C, P> = React.JSX.LibraryManagedAttributes<C, P>;
    type IntrinsicAttributes = React.JSX.IntrinsicAttributes;
    type IntrinsicClassAttributes<T> = React.JSX.IntrinsicClassAttributes<T>;
    type IntrinsicElements = React.JSX.IntrinsicElements;
  }
}
