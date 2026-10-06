/** Router path for any @id.
 *
 * ARKs, DOIs and UUIDs are legal path text as they are, so they stay
 * readable in the address bar. Two kinds of character are escaped, and the router
 * decodes each back into the `*` param:
 * - `%`, `?` and `#`, which would be decoded or end the path early;
 * - any `/` straight after another `/` (the `//` in `https://` and
 *   `file:///`), which react-router's Link would collapse into one.
 */
export const viewPath = (id: string) =>
  "/view/" +
  id.replace(/[%?#]/g, encodeURIComponent).replace(/(?<=\/)\//g, "%2F");
