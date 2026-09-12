import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

/**
 * Redirection http → https, explicite.
 *
 * Vercel la fait déjà pour les domaines qu'il sert. Elle est doublée ici pour
 * deux raisons : un chemin qui échapperait à la règle de la plateforme (un
 * proxy en amont, un domaine ajouté à la main, un déploiement ailleurs) ne
 * doit pas servir l'app en clair une seule fois — et c'est la première requête
 * en clair, celle d'avant HSTS, qui est la dangereuse.
 *
 * `x-forwarded-proto` et pas `request.nextUrl.protocol` : derrière un
 * terminaison TLS, l'application voit toujours du http, et se fier à l'URL
 * interne donnerait une boucle de redirection infinie.
 *
 * En développement on ne redirige rien : `localhost` n'a pas de certificat, et
 * une redirection y rendrait le site inaccessible.
 */
export function middleware(request: NextRequest) {
  const proto = request.headers.get("x-forwarded-proto");
  const host = request.headers.get("host") ?? "";
  const local =
    host.startsWith("localhost") ||
    host.startsWith("127.0.0.1") ||
    host.startsWith("[::1]");

  if (proto === "http" && !local) {
    const url = request.nextUrl.clone();
    url.protocol = "https:";
    // 308 : la méthode et le corps sont conservés, et le navigateur mémorise.
    return NextResponse.redirect(url, 308);
  }

  return NextResponse.next();
}

export const config = {
  // Tout, sauf les fichiers immuables de Next et les icônes : les faire passer
  // par le middleware coûterait un aller-retour de calcul par image.
  matcher: ["/((?!_next/static|_next/image|icons|favicon.ico).*)"],
};
