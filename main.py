import requests
from bs4 import BeautifulSoup
import re
import os
import hashlib

BASE_URL = "https://www.cosina.co.jp/voigtlander/"
CACHE_DIR = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)


# Fetch with caching
def fetch_with_cache(url):
    cache_key = hashlib.md5(url.encode("utf-8")).hexdigest()
    cache_path = os.path.join(CACHE_DIR, cache_key + ".html")

    if os.path.exists(cache_path):
        with open(cache_path, "r", encoding="utf-8") as f:
            return f.read()

    response = requests.get(url)
    response.raise_for_status()
    content = response.text

    with open(cache_path, "w", encoding="utf-8") as f:
        f.write(content)

    return content


# Step 1: Extract mount pages from homepage dynamically
def get_mount_pages():
    content = fetch_with_cache(BASE_URL)
    soup = BeautifulSoup(content, "html.parser")
    mounts = {}
    for item in soup.select("li.voi-type__item a.voi-type__item-link"):
        url = item["href"]
        mount_name = item.select_one(".voi-type__item-name").get_text(strip=True)
        if mount_name == "ACCESSORIES":
            continue
        mounts[mount_name] = url
    return mounts


# Get lens links from each mount page
def get_lens_links(mount_url):
    content = fetch_with_cache(mount_url)
    soup = BeautifulSoup(content, "html.parser")
    lens_links = set()
    for a in soup.select('a[href*="voigtlander"]'):
        link = a["href"]
        if link.startswith(mount_url) and link.rstrip("/") != mount_url.rstrip("/"):
            lens_links.add(link)
    return lens_links


# Convert lens construction to Wikipedia format
def format_lens_const(japanese_const):
    groups_elements = re.match(r"(\d+)群(\d+)枚", japanese_const)
    if groups_elements:
        groups, elements = groups_elements.groups()
        return f"{elements}e/{groups}g"
    return japanese_const


# Format numeric values for Wikipedia
def format_cvt(value, unit):
    numeric_values = re.findall(r"[\d\.]+", value)

    unit_target = {"m": "m|ft"}.get(unit, unit)
    if "×" in value:
        return f"{{{{cvt|{'|×|'.join(numeric_values)}|{unit_target}}}}}"
    elif numeric_values:
        return f"{{{{cvt|{numeric_values[0]}|{unit_target}}}}}"
    return value


# Format f-number to Wikipedia template
def format_f_number(value):
    match = re.search(r"1 ?: ?([\d\.]+)", value)
    return f"{{{{f/|{match.group(1)}}}}}" if match else value


def format_focal(value):
    value = value.replace("mm", "")
    value = value.replace("約", "")
    dx = "フルサイズ換算:"

    preamble = ""
    if dx in value:
        ff_value = value.split(dx)[1][:-1]
        value = value.replace(dx, "full frame equivalent: ")
        preamble = f'data-sort-value="{ff_value}"'
    else:
        ff_value = value
    ff_value = float(ff_value)

    if ff_value < 21:
        color = "fdd"
    elif ff_value < 40:
        color = "fed"
    elif ff_value < 65:
        color = "ffd"
    else:
        color = "dfd"
    preamble = f'! style = "background:#{color};" ' + preamble
    return preamble + "|" + value


# Parse individual lens page for specifications based on provided HTML structure
def parse_lens_page(lens_url):
    content = fetch_with_cache(lens_url)
    soup = BeautifulSoup(content, "html.parser")
    specs = {"reference": lens_url}
    spec_data = soup.select(
        ".lens-specification__detail__data .lens-specification__detail__data-unit"
    )
    for item in spec_data:
        header = item.select_one(
            ".lens-specification__detail__data-unitDt"
        ).text.strip()
        value = item.select_one(".lens-specification__detail__data-unitDd").text.strip()
        if header == "焦点距離":
            specs["focal_length"] = format_focal(value)
        elif header == "口径比":
            specs["f_number"] = format_f_number(value)
        elif header == "最短撮影距離":
            specs["min_focus"] = format_cvt(value, "m")
        elif header == "レンズ構成":
            specs["lens_const"] = format_lens_const(value)
        elif header == "絞り羽根枚数":
            specs["aperture_blades"] = value.split("枚")[0].strip()
        elif header == "最大径×全長":
            specs["dimensions"] = format_cvt(value, "mm")
        elif header == "重量":
            specs["weight"] = format_cvt(value, "g")
        elif header in ["フィルター", "フィルター径", "フィルター", "フィルターサイズ"]:
            if "不可" in value:
                value = "N/A"
            specs["filter_size"] = value
    lens_name = soup.select_one(".lens-mv__group__category").text.strip().title()
    lens_suffix = " ".join(
        soup.select_one(".lens-mv__group__model").text.strip().split(" ")[2:]
    )

    specs["name"] = " ".join([lens_name, lens_suffix])
    return specs


# Crawl each mount and generate Wikipedia-formatted table
def crawl_mount(mount_url, mount_name):
    lenses = []
    lens_links = get_lens_links(mount_url)
    for lens_link in lens_links:
        lens_specs = parse_lens_page(lens_link)
        lenses.append(lens_specs)

    lenses.sort(
        key=lambda x: float(re.findall(r"[\d\.]+", x.get("focal_length", "0"))[0])
    )

    table = f'{{| class="wikitable sortable" style="font-size:100%;text-align:center;"\n|+ Cosina Voigtländer lenses for [[{mount_name}]]<ref>{{{{Cite web |url={mount_url} |title={mount_name} Lenses |access-date=2024-03-12|website=Cosina Voigtländer}}}}</ref>\n'
    table += '! [[Focal length]] (mm) !! [[F-number]] !! Min. focus !! Name !! Lens const. !! [[Diaphragm (optics)|Aperture blades]] !! Dimensions (Diam.×Length) !! Weight !! [[Photographic filter#Filter sizes and mountings|Filter size]] !! class="unsortable" | Ref.\n'

    for lens in lenses:
        table += "|-\n"
        table += f"| {lens.get('focal_length', '')}\n| {lens.get('f_number', '')}\n| {lens.get('min_focus', '')}\n| {lens.get('name', '').replace('Aspherical', '[[aspheric lens|Asph.]]')}\n| {lens.get('lens_const', '')}\n| {lens.get('aperture_blades', '')}\n| {lens.get('dimensions', '')}\n| {lens.get('weight', '')}\n| {lens.get('filter_size', '')}\n| <ref>{{{{cite web|url={lens.get('reference')}|title={lens.get('name')}|website=Cosina Voigtländer|access-date=2024-03-12}}}}</ref>\n"

    table += "|}"

    print(table)


# Main function to orchestrate the crawling
def main():
    mounts = get_mount_pages()
    for mount_name, mount_url in mounts.items():
        crawl_mount(mount_url, mount_name)


if __name__ == "__main__":
    main()
