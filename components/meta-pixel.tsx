import Script from "next/script";

/**
 * Meta Pixel.
 *
 * Two deliberate choices:
 *
 * 1. `next/script` with `afterInteractive` rather than the raw <script> block
 *    Meta hands out. In the App Router a bare inline script in the body is
 *    re-executed on client navigation, which double-counts PageView on every
 *    route change — and this site has four routes people move between.
 *
 * 2. Production only. Without this, `next dev` and every preview build fire
 *    real PageView events into the same pixel, and the first thing you would
 *    "learn" from the data is your own laptop.
 *
 * The pixel id is not a secret — it ships in the HTML of every page that loads
 * it, by design. It is inline rather than an env var so that a deploy which
 * forgets to set a variable fails visibly at review rather than silently
 * collecting nothing.
 *
 * NOTE: this sends visitor data to Meta. `app/privacy/page.tsx` has to say so —
 * see the "Website analytics" section added alongside this.
 */
const PIXEL_ID = "2259641408140712";

export function MetaPixel() {
  if (process.env.NODE_ENV !== "production") return null;

  return (
    <>
      <Script id="meta-pixel" strategy="afterInteractive">
        {`!function(f,b,e,v,n,t,s)
{if(f.fbq)return;n=f.fbq=function(){n.callMethod?
n.callMethod.apply(n,arguments):n.queue.push(arguments)};
if(!f._fbq)f._fbq=n;n.push=n;n.loaded=!0;n.version='2.0';
n.queue=[];t=b.createElement(e);t.async=!0;
t.src=v;s=b.getElementsByTagName(e)[0];
s.parentNode.insertBefore(t,s)}(window, document,'script',
'https://connect.facebook.net/en_US/fbevents.js');
fbq('init', '${PIXEL_ID}');
fbq('track', 'PageView');`}
      </Script>
      <noscript>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          height="1"
          width="1"
          style={{ display: "none" }}
          alt=""
          src={`https://www.facebook.com/tr?id=${PIXEL_ID}&ev=PageView&noscript=1`}
        />
      </noscript>
    </>
  );
}
