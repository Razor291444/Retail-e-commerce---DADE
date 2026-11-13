import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./style.css";
type Product = { productId?: number; barcode: string; name: string; brand?: string; imageUrl?: string; price: number };
const query = `{ products(limit: 24) { productId barcode name brand imageUrl price } }`;
function App() {
  const [products, setProducts] = useState<Product[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    fetch("/graphql", {method:"POST",headers:{"content-type":"application/json"},body:JSON.stringify({query})})
      .then(async r => {if(!r.ok) throw new Error("Catalogue indisponible");return r.json();})
      .then(data => setProducts(data.data.products)).catch(e => setError(e.message));
  }, []);
  return <main><header><h1>ReMarket</h1><nav>Catalogue · Panier · Connexion · Administration</nav></header>
    <section><h2>Produits alimentaires</h2>{error && <p className="error">{error}</p>}
      <div className="grid">{products.map(p => <article key={p.barcode}><img src={p.imageUrl} /><h3>{p.name}</h3><p>{p.brand || "Marque inconnue"}</p><strong>{p.price.toFixed(2)} €</strong><button>Ajouter au panier</button></article>)}</div></section></main>;
}
createRoot(document.getElementById("root")!).render(<React.StrictMode><App /></React.StrictMode>);
