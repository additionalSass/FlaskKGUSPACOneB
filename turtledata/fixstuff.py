from rdflib import Graph, URIRef, Literal, Namespace

input_file = "output.ttl"
output_file = "local_data.ttl"

g = Graph()
g.parse(input_file, format="turtle")

BASE = Namespace("http://example.org/mybase#")
OWL = Namespace("http://www.w3.org/2002/07/owl#")

for s, p, o in g:
    if p == OWL.sameAs and isinstance(o, Literal):
        # Check if the literal is a valid URI
        uri_str = str(o)
        if uri_str.startswith("http://"):
            new_o = URIRef(uri_str)
            g.remove((s, p, o))  # Remove the old triple
            g.add((s, p, new_o))  # Add the updated triple
            print(f"Updated {s} {p} {o} -> {new_o}")

g.serialize(destination=output_file, format="turtle")
print(f"Updated TTL file saved as {output_file}")