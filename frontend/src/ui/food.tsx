// A dish's picture: its photo, or (until a photo is uploaded) a neutral tile with a simple line icon
// for the kind of dish. No emoji: clean, like Uber Eats / PickMe Food.
import { Beef, Beer, CakeSlice, Citrus, Coffee, Croissant, CupSoda, Drumstick, EggFried, Fish, Hamburger, IceCreamCone, Milk, Pizza, Popcorn, Salad, Sandwich, Soup, Utensils, Wine, type LucideIcon } from "lucide-react";

const ICONS: [RegExp, LucideIcon][] = [
  [/burger/i, Hamburger],
  [/pizza/i, Pizza],
  [/salad/i, Salad],
  [/soup|kottu|noodle|pasta|spaghetti|rice|biriyani|biryani|curry|dhal|dal/i, Soup],
  [/hopper|appa|string|roti|paratha|naan|bread|toast/i, Croissant],
  [/sandwich|wrap|sub/i, Sandwich],
  [/fries|chips|snack|bite/i, Popcorn],
  [/chicken|wing|drumstick/i, Drumstick],
  [/steak|beef|meat|lamb|mutton|pork/i, Beef],
  [/fish|prawn|crab|seafood|cuttle|squid/i, Fish],
  [/egg|omelet|breakfast/i, EggFried],
  [/cake|dessert|pudding|watalappan|sweet/i, CakeSlice],
  [/ice ?cream|sundae/i, IceCreamCone],
  [/coffee|latte|cappuccino|espresso|tea/i, Coffee],
  [/milo|milk|shake|lassi/i, Milk],
  [/juice|lime|lemon|orange|mango|passion/i, Citrus],
  [/beer/i, Beer],
  [/wine/i, Wine],
  [/coke|cola|soda|sprite|fanta|ginger beer|drink|beverage|water/i, CupSoda],
];

const TINTS: [string, string, string][] = [
  ["#fff4e5", "#ffe8c7", "#b26a00"], // amber
  ["#eaf6ee", "#d3eedd", "#0a7a43"], // green
  ["#e9f1ff", "#d6e4ff", "#2556c4"], // blue
  ["#f6f1ea", "#ece3d6", "#7a5c3a"], // sand
  ["#f3eefc", "#e6dcfa", "#6b3fb8"], // violet
  ["#eef3f5", "#dde6ea", "#41606d"], // slate
];

export function dishIcon(...names: (string | undefined)[]): LucideIcon {
  for (const n of names) for (const [re, I] of ICONS) if (n && re.test(n)) return I;
  return Utensils;
}

/** Kept for older callers: the icon's name. */
export const foodEmoji = (...names: (string | undefined)[]): string => dishIcon(...names).displayName ?? "Utensils";

/** Dish picture. `round` for small thumbnails in lists; square-ish tiles otherwise. */
export function Dish({ src, name, hint, size = 96, round = false, className = "" }: { src?: string | null; name: string; hint?: string; size?: number; round?: boolean; className?: string }) {
  const shape = round ? "rounded-full" : size >= 80 ? "rounded-2xl" : "rounded-xl";
  if (src) return <img src={src} alt="" loading="lazy" className={`shrink-0 bg-ink/[.05] object-cover ${shape} ${className}`} style={{ width: size, height: size }} />;
  const Icon = dishIcon(name, hint);
  // Until a photo is uploaded: a soft tint (one of a few calm hues, picked from the name) with a fine
  // line icon, so a menu without photos still looks designed rather than empty.
  const hue = TINTS[[...name].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 7) % TINTS.length];
  return (
    <span aria-hidden className={`grid shrink-0 place-items-center ${shape} ${className}`} style={{ width: size, height: size, background: `linear-gradient(145deg, ${hue[0]}, ${hue[1]})`, color: hue[2] }}>
      <Icon size={Math.round(size * 0.36)} strokeWidth={1.6} />
    </span>
  );
}
