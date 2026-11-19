const SOLES = new Intl.NumberFormat("es-PE", { style: "currency", currency: "PEN", maximumFractionDigits: 2 });

export const soles = (x) => (x === null || x === undefined ? "-" : SOLES.format(x));
export const pct = (x) => (x === null || x === undefined ? "-" : (x * 100).toFixed(2) + " %");
export const fecha = (iso) => (iso ? new Date(iso).toLocaleString("es-PE", { dateStyle: "short", timeStyle: "short" }) : "-");
export const fechaCorta = (ymd) => (ymd ? ymd.split("-").reverse().join("/") : "-");
export const dniDe = (documento) => (documento ? documento.replace("DNI#", "") : "-");
