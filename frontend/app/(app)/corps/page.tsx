import { redirect } from "next/navigation";

/** « Corps » a éclaté en Training et Nutrition le 13/09. Les objectifs
 *  mesurés et les formules sont passés dans Training, qui prend la suite. */
export default function CorpsPage() {
  redirect("/training");
}
