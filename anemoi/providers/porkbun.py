from typing import Dict, List

import requests

from anemoi.providers import Provider
from anemoi.util import anlog, is_ip_record_valid


class PorkbunProvider(Provider):
    # https://porkbun.com/api/json/v3/documentation
    uri = "https://api.porkbun.com/api/json/"
    version = "v3"
    key: str = None
    secret: str = None

    def __init__(self, config):
        if (apikey := config.get("apikey")) and (secret := config.get("secret")):
            self.key = apikey
            self.secret = secret
        else:
            anlog.error("Insufficient credentials for Porkbun")
            return None

    def _post(self, endpoint, data=None):
        if not data:
            data = {}
        data.update({"apikey": self.key, "secretapikey": self.secret})
        res = requests.post(f"{self.uri}{self.version}/{endpoint}", json=data)
        if res.status_code != 200:
            try:
                if (output := res.json()) and output.get("status", "") == "ERROR":
                    raise Exception(
                        f"Error {res.status_code} on Porkbun API: {output.get('message','unknown')}"
                    )
            except requests.exceptions.JSONDecodeError:
                raise Exception(f"Unknown error {res.status_code} on Porkbun API.")
        data = res.json()
        if data.get("status", "") != "SUCCESS":
            raise Exception("Unknown error in Porkbun API")
        data.pop("status", None)
        return data

    # Returns the root domain corresponding to the given subdomain,
    # and all records associated with the subdomain
    def __get_records(self, subdomain) -> Tuple[str, str, List[str]]:
        parts = subdomain.split(".")
        for i in range(len(parts)):
            domain = ".".join(parts[i:])
            try:
                res = self._post(f"dns/retrieve/{domain}")
                raw_records = res.get("records", [])
                targets = [x for x in raw_records if x.get("name", "") == subdomain]
                sub = ".".join(parts[:i])
                return sub, domain, targets
            except Exception as e:
                anlog.info(e)
        raise Exception(f"subdomain {subdomain} is invalid")

    # returns list of {'A': '1.1.1.1'} objects
    def get_record_ips(self, subdomain) -> List[Dict[str, str]]:
        result = []
        _, _, recs = self.__get_records(subdomain)
        for rec in recs:
            if (kind := rec.get("type")) and (ip := rec.get("content")):
                result.append({kind: ip})
        return result

    # returns bool of if the update succeeded or not
    def update_record_ip(self, subdomain: str, ip, rtype="A") -> bool:
        if not is_ip_record_valid(ip, rtype):
            return False
        name, domain, recs = self.__get_records(subdomain)
        try:
            if recs:
                recs = [x for x in recs if x.get("type", "") == rtype]
            else:
                # need to create record
                res = self._post(
                    f"dns/create/{domain}", {"name": name, "type": rtype, "content": ip}
                )
                if "id" not in res:
                    anlog.error(f"Failed to create record for {subdomain}")
                    return False
                return True
            for rec in recs:
                if ip == rec.get("content", ""):
                    continue
                res = self._post(
                    f"dns/editByNameType/{domain}/{rtype}/{name}", {"content": ip}
                )
                return True
        except Exception as e:
            anlog.error(e)
        return False

